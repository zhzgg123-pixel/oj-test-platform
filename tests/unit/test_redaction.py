import json
from pathlib import Path

from core_engine.executor.base_executor import TaskResult
from core_engine.report_engine.report_generator import ReportGenerator
from tests.unit.test_reports import failed_result


def test_report_drops_credentials_and_unknown_config_fields(tmp_path):
    info = ReportGenerator(tmp_path).generate(TaskResult(), {'seed': 17, 'password': 'secret-password',
        'session_id': 'session-value', 'extra': {'Authorization': 'Bearer token-value'}})
    data = json.loads(Path(info['json_path']).read_text(encoding='utf-8'))
    assert data['config'] == {'seed': 17}
    assert 'secret-password' not in Path(info['html_path']).read_text(encoding='utf-8')


def test_report_redacts_known_secrets_and_marks_modified_source(tmp_path):
    result = failed_result()
    result.case_results[0].error_message = 'failure test-secret-must-not-leak'
    source = result.case_results[0].case.code
    info = ReportGenerator(tmp_path).generate(result, secrets=('test-secret-must-not-leak', 'return 1'))
    for format in ('html', 'json'):
        text = Path(info[f'{format}_path']).read_text(encoding='utf-8')
        assert 'test-secret-must-not-leak' not in text
        assert 'return 1' not in text
    data = json.loads(Path(info['json_path']).read_text(encoding='utf-8'))
    case = data['all_cases'][0]
    assert case['input']['source_redacted'] is True
    assert case['input']['source_sha256'] == result.case_results[0].case.source_sha256
    assert result.case_results[0].case.code == source


def test_shared_redactor_masks_nested_fields_without_mutating_input():
    from core_engine.redaction import redact
    value = {'nested': [{'Cookie': 'session=x', 'detail': 'long-secret short'}], 'authorization': 'secret'}
    clean = redact(value, ('short', 'long-secret'))
    assert clean['nested'][0] == {'Cookie': '[REDACTED]', 'detail': '[REDACTED] [REDACTED]'}
    assert clean['authorization'] == '[REDACTED]'
    assert value['nested'][0]['Cookie'] == 'session=x'


def test_redaction_does_not_rewrite_schema_keys_or_its_own_marker():
    from core_engine.redaction import redact
    assert redact({'input': 'input long-secret'}, ('input', 'long-secret', 'RE')) == {
        'input': '[REDACTED] [REDACTED]'}


def test_short_secret_does_not_corrupt_identifiers_hashes_or_verdicts(tmp_path):
    result = failed_result()
    info = ReportGenerator(tmp_path).generate(result, secrets=('a', 'AC', 'FAILED'))
    data = json.loads(Path(info['json_path']).read_text(encoding='utf-8'))
    assert data['report_id'] == info['report_id']
    case = data['all_cases'][0]
    assert case['input']['source_sha256'] == result.case_results[0].case.source_sha256
    assert case['input']['profile_sha256'] == 'a' * 64
    assert case['expectation']['verdict'] == 'AC'
    assert case['status'] == 'FAILED'


def test_filtered_credential_value_is_redacted_from_surviving_diagnostics(tmp_path):
    from core_engine.contracts import Observation
    result = failed_result()
    result.case_results[0].observation = Observation(kind='verdict', verdict='WA', evidence={
        'token': 'diagnostic-token-42', 'detail': 'echo diagnostic-token-42'})
    result.case_results[0].error_message = 'also diagnostic-token-42'
    info = ReportGenerator(tmp_path).generate(result)
    for format in ('json', 'html'):
        assert 'diagnostic-token-42' not in Path(info[f'{format}_path']).read_text(encoding='utf-8')


def test_custom_error_code_secret_is_not_exposed_in_distribution_keys(tmp_path):
    from core_engine.contracts import Observation
    result = failed_result()
    result.case_results[0].observation = Observation(kind='protocol_error', error_code='secret-error-42')
    result.case_results[0].actual_status = 'secret-error-42'
    info = ReportGenerator(tmp_path).generate(result, secrets=('secret-error-42',))
    data = Path(info['json_path']).read_text(encoding='utf-8')
    assert 'secret-error-42' not in data
    assert sum(json.loads(data)['summary']['status_distribution'].values()) == 1
