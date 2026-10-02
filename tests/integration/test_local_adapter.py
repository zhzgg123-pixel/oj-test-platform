"""Protocol failures must be represented immediately, without phantom polling."""
from dataclasses import asdict

import pytest

from core_engine.case_engine.base_generator import TestCase as OJCase
from core_engine.contracts import Expectation
from core_engine.executor.sequential_executor import SequentialExecutor
from plugins.local_oj.adapter import LocalOJAdapter

pytestmark = pytest.mark.integration


@pytest.fixture
def adapter_factory(mock_oj_factory):
    adapters = []
    def make(**kwargs):
        server = mock_oj_factory(**kwargs)
        adapter = LocalOJAdapter(server.base_url, timeout=0.1)
        assert adapter.login('tester', 'test-only').success
        adapters.append(adapter)
        return adapter, server
    yield make
    for adapter in adapters:
        adapter._client._session.close()


@pytest.mark.parametrize('problem,code,expected_code', [
    ('999999', 'int main(){}', 'PROBLEM_NOT_FOUND'), ('1', '', 'CODE_REQUIRED'),
])
def test_http_200_business_error_is_not_submission_success(adapter_factory, problem, code, expected_code):
    adapter, _ = adapter_factory()
    result = adapter.submit_code(problem, code)
    assert result.success is False
    assert result.observation.kind == 'business_error'
    assert result.observation.http_status == 200
    assert result.observation.error_code == expected_code


@pytest.mark.parametrize('payload,expected_code', [
    ({}, 'MISSING_VERDICT'),
    ([], 'INVALID_RESPONSE_SHAPE'),
    ({'result': 'mystery'}, 'UNKNOWN_VERDICT'),
    ({'success': False, 'error': 'unrecognized server error'}, 'UNKNOWN_BUSINESS_ERROR'),
    ({'result': 'AC', 'total': 'two'}, 'INVALID_METRICS'),
    ({'result': 'AC', 'passed': 3, 'total': 2}, 'INVALID_METRICS'),
])
def test_invalid_protocol_response_is_not_polled(adapter_factory, payload, expected_code):
    adapter, server = adapter_factory(response_override=payload)
    case = OJCase('protocol', 'invalid response', '1', 'int main(){}')
    result = SequentialExecutor(poll_interval=0.01, poll_timeout=0.1).execute(
        [case], adapter, login_required=False)
    assert result.error == 1
    observation = result.case_results[0].observation
    assert observation.kind == 'protocol_error'
    assert observation.error_code == expected_code
    assert len([r for r in server.requests if r['path'].startswith('/api/submit/')]) == 1


@pytest.mark.parametrize('scenario,kind,code', [
    ('malformed', 'protocol_error', 'INVALID_JSON'),
    ('slow', 'transport_error', 'READ_TIMEOUT'),
    ('disconnect', 'transport_error', 'CONNECTION_ERROR'),
])
def test_network_and_parse_failures_keep_their_kind(adapter_factory, scenario, kind, code):
    adapter, server = adapter_factory(scenario=scenario, delay=0.3)
    result = adapter.submit_code('1', 'int main(){}')
    assert result.observation.kind == kind
    assert result.observation.error_code == code
    assert result.success is False
    assert len([r for r in server.requests if r['path'].startswith('/api/submit/')]) == 1


def test_exact_rejection_expectation_passes_through_executor(adapter_factory):
    adapter, _ = adapter_factory()
    case = OJCase('not-found', 'missing problem', '999999', 'int main(){}',
                  expectation=Expectation(kind='business_error', http_status=200, error_code='PROBLEM_NOT_FOUND'))
    result = SequentialExecutor().execute([case], adapter, login_required=False)
    assert result.passed == 1
    assert result.case_results[0].observation.error_code == 'PROBLEM_NOT_FOUND'


def test_unauthorized_is_a_specific_http_result(mock_oj):
    adapter = LocalOJAdapter(mock_oj.base_url, timeout=1)
    try:
        case = OJCase('anonymous', 'auth rejection', '1', 'int main(){}',
                      expectation=Expectation(kind='http_error', http_status=401))
        result = SequentialExecutor().execute([case], adapter, login_required=False)
        assert result.passed == 1
        assert result.case_results[0].observation.http_status == 401
    finally:
        adapter._client._session.close()


def test_sync_results_belong_to_receipt_not_shared_last_slot(adapter_factory):
    adapter, _ = adapter_factory()
    first = adapter.submit_code('1', '// verdict:AC')
    second = adapter.submit_code('1', '// verdict:WA')
    assert first.judge_result.status == 'AC'
    assert second.judge_result.status == 'WA'
    assert adapter.get_judge_result('unrelated-id') is None
    assert adapter.get_judge_result('') is None


def test_receipt_exposes_immediate_observation(adapter_factory):
    adapter, _ = adapter_factory()
    case = OJCase('receipt', 'synchronous receipt', '1', '// verdict:AC')
    receipt = adapter.submit_case(case)
    assert receipt.immediate_observation.verdict == 'AC'
    assert receipt.submission_id


def test_raw_response_does_not_retain_auth_fields(adapter_factory):
    adapter, _ = adapter_factory(response_override={
        'result': 'AC', 'password': 'never-save-me', 'Cookie': 'session=private', 'total': 1, 'passed': 1})
    result = adapter.submit_code('1', '// verdict:AC')
    assert 'never-save-me' not in str(asdict(result))
    assert 'session=private' not in str(asdict(result))


def test_failed_reauthentication_clears_previous_session(adapter_factory):
    adapter, _ = adapter_factory()
    assert adapter.login('tester', 'wrong').success is False
    rejected = adapter.submit_code('1', 'int main(){}')
    assert rejected.observation.kind == 'http_error'
    assert rejected.observation.http_status == 401


@pytest.mark.parametrize('status,kind', [(401, 'http_error'), (503, 'http_error'), (307, 'protocol_error')])
def test_http_status_survives_adapter_parsing(adapter_factory, status, kind):
    adapter, server = adapter_factory(submit_status=status)
    result = adapter.submit_code('1', 'int main(){}')
    assert result.observation.kind == kind
    assert result.observation.http_status == status
    assert len([r for r in server.requests if r['path'].startswith('/api/submit/')]) == 1


def test_close_releases_authentication(adapter_factory):
    adapter, _ = adapter_factory()
    adapter.close()
    assert not adapter._client.cookies
