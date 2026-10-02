import hashlib
import json
from pathlib import Path

from core_engine.case_engine.base_generator import TestCase as Case
from core_engine.contracts import Expectation, Observation
from core_engine.executor.base_executor import CaseResult, TaskResult
from core_engine.report_engine.report_generator import ReportGenerator


def failed_result():
    case = Case(id='case-1', desc='<img src=x onerror=alert(1)>', problem_id='2',
                code='// <script>alert(1)</script>\nint main(){return 1;}', seed=123,
                profile_id='max_of_two', profile_sha256='a' * 64,
                expectation=Expectation(kind='verdict', verdict='AC'))
    result = CaseResult(case=case, status='FAILED', actual_status='WA',
                        observation=Observation(kind='verdict', verdict='WA', http_status=200),
                        error_message='expected AC < actual WA', start_time=1, end_time=2)
    return TaskResult(total=1, failed=1, case_results=[result], start_time=1, end_time=2)


def test_report_preserves_reproduction_input_and_structured_difference(tmp_path):
    result = failed_result()
    info = ReportGenerator(tmp_path).generate(result, {'seed': 123})
    data = json.loads(Path(info['json_path']).read_text(encoding='utf-8'))
    case = data['all_cases'][0]
    assert case['input']['code'] == result.case_results[0].case.code
    assert case['input']['source_sha256'] == hashlib.sha256(case['input']['code'].encode()).hexdigest()
    assert case['input']['seed'] == 123
    assert case['expectation']['verdict'] == 'AC'
    assert case['observation']['verdict'] == 'WA'
    assert case['observation']['http_status'] == 200
    assert case['error'] == 'expected AC < actual WA'
    assert case['attempt_count'] == 1
    assert data['failed_cases'][0]['input'] == case['input']


def test_html_escapes_all_dynamic_case_text_and_shows_evidence(tmp_path):
    info = ReportGenerator(tmp_path).generate(failed_result())
    body = Path(info['html_path']).read_text(encoding='utf-8')
    assert '<script>alert(1)</script>' not in body
    assert '<img src=x' not in body
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in body
    assert 'expected AC &lt; actual WA' in body
    assert 'max_of_two' in body and '123' in body


def test_repeated_generation_does_not_overwrite_existing_reports(tmp_path, monkeypatch):
    from datetime import datetime
    from core_engine.report_engine import report_generator
    class FixedClock:
        @staticmethod
        def now():
            return datetime(2026, 10, 2, 12, 0, 0)
    monkeypatch.setattr(report_generator, 'datetime', FixedClock)
    generator = ReportGenerator(tmp_path)
    first = generator.generate(failed_result())
    original = Path(first['json_path']).read_bytes()
    second = generator.generate(TaskResult(total=1, passed=1))
    assert first['report_id'] != second['report_id']
    assert Path(first['json_path']).read_bytes() == original
    assert len(list(tmp_path.glob('*.json'))) == 2


def test_invalid_legacy_expectation_still_produces_error_report(tmp_path):
    case = Case(id='legacy', desc='invalid expectation', problem_id='1', code='', expected_status='ERROR')
    result = TaskResult(total=1, error=1, case_results=[CaseResult(
        case=case, status='ERROR', error_message='INVALID_EXPECTATION', attempt_count=0)])
    info = ReportGenerator(tmp_path).generate(result)
    data = json.loads(Path(info['json_path']).read_text(encoding='utf-8'))
    assert data['all_cases'][0]['expectation'] is None
    assert data['all_cases'][0]['expected'] == 'ERROR'
    assert data['all_cases'][0]['error'] == 'INVALID_EXPECTATION'
