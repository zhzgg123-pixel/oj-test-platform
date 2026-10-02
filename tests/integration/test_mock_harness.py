"""The HTTP test boundary must model actual cpp-oj authentication and responses."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
import requests

from plugins.local_oj.adapter import LocalOJAdapter
from tests.helpers import wait_until

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('verdict', ['AC', 'WA', 'CE', 'TLE', 'RE'])
def test_adapter_reads_full_synchronous_verdict(mock_oj, verdict):
    adapter = LocalOJAdapter(mock_oj.base_url, timeout=2)
    try:
        assert adapter.login('tester', 'test-only').success
        result = adapter.submit_code('1', f'// verdict:{verdict}\nint main() {{}}')
        assert result.success
        assert result.judge_result.status == verdict
        assert result.judge_result.total == 2
        assert result.judge_result.passed == (2 if verdict == 'AC' else 0)
        assert result.judge_result.raw_response['compile_error'] == (
            'mock compilation error' if verdict == 'CE' else None)
    finally:
        adapter._client._session.close()  # Existing adapter has no close API yet (S02).


def test_cookie_auth_and_business_rejection_are_distinct(mock_oj, http_session):
    endpoint = mock_oj.base_url + '/api/submit/999999'
    anonymous = http_session.post(endpoint, data={'code': 'int main(){}'}, timeout=2)
    assert anonymous.status_code == 401
    assert anonymous.json()['error'] == 'Not authenticated'
    login = http_session.post(mock_oj.base_url + '/api/login',
                              json={'username': 'tester', 'password': 'test-only'}, timeout=2)
    assert login.json()['success'] is True
    rejected = http_session.post(endpoint, data={'code': 'int main(){}', 'lang': 'cpp'}, timeout=2)
    assert rejected.status_code == 200
    assert rejected.json() == {'success': False, 'error': 'Problem not found'}
    assert 'test-only' not in json.dumps(mock_oj.requests)
    assert http_session.cookies.get('session_id') not in json.dumps(mock_oj.requests)


def test_failed_login_does_not_authenticate(mock_oj, http_session):
    login = http_session.post(mock_oj.base_url + '/api/login',
                              data={'username': 'tester', 'password': 'wrong'}, timeout=2)
    assert login.status_code == 200
    assert login.json()['success'] is False
    assert not http_session.cookies


def test_empty_source_is_business_error_not_compile_error(mock_oj, logged_in_session):
    result = logged_in_session.post(mock_oj.base_url + '/api/submit/1',
                                     data={'code': '', 'lang': 'cpp'}, timeout=2)
    assert result.json() == {'success': False, 'error': 'Code is required'}


def test_barrier_exposes_real_overlapping_http_requests(mock_oj):
    def submit():
        with requests.Session() as client:
            client.trust_env = False
            client.post(mock_oj.base_url + '/api/login',
                        data={'username': 'tester', 'password': 'test-only'}, timeout=2)
            return client.post(mock_oj.base_url + '/api/submit/1',
                               data={'code': '// verdict:AC'}, timeout=3).json()['result']
    mock_oj.block_submissions()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(submit) for _ in range(2)]
        try:
            wait_until(lambda: mock_oj.max_active_submissions == 2, timeout=2)
        finally:
            mock_oj.release_submissions()
        assert [job.result(timeout=3) for job in jobs] == ['AC', 'AC']


@pytest.mark.parametrize('scenario,exception', [
    ('slow', requests.Timeout), ('disconnect', requests.ConnectionError),
])
def test_transport_faults_are_not_valid_http_success(mock_oj_factory, http_session, scenario, exception):
    server = mock_oj_factory(scenario=scenario, delay=0.3)
    http_session.post(server.base_url + '/api/login',
                      data={'username': 'tester', 'password': 'test-only'}, timeout=2)
    with pytest.raises(exception):
        http_session.post(server.base_url + '/api/submit/1', data={'code': 'int main(){}'}, timeout=0.05)


def test_malformed_body_can_reach_adapter_boundary(mock_oj_factory, http_session):
    server = mock_oj_factory(scenario='malformed')
    http_session.post(server.base_url + '/api/login',
                      data={'username': 'tester', 'password': 'test-only'}, timeout=2)
    result = http_session.post(server.base_url + '/api/submit/1', data={'code': 'x'}, timeout=2)
    assert result.status_code == 200
    with pytest.raises(requests.exceptions.JSONDecodeError):
        result.json()


def test_shutdown_releases_listener_and_worker_threads(mock_oj_factory, http_session):
    for _ in range(2):
        server = mock_oj_factory()
        url = server.base_url
        assert http_session.get(url + '/', timeout=1).status_code == 200
        server.close()
        assert not server.is_running
        with pytest.raises(requests.ConnectionError):
            http_session.get(url + '/', timeout=0.2)
