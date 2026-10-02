"""Regression for the original expected_status=ERROR false positives."""
import pytest

from core_engine.case_engine.base_generator import TestCase as OJCase
from core_engine.executor.sequential_executor import SequentialExecutor
from plugins.local_oj.adapter import LocalOJAdapter

pytestmark = pytest.mark.integration


def test_legacy_generic_error_cannot_pass_for_actual_ac(mock_oj):
    adapter = LocalOJAdapter(mock_oj.base_url, timeout=1)
    case = OJCase(id='legacy-error', desc='ambiguous expectation', problem_id='1',
                  code='// verdict:AC', expected_status='ERROR')
    try:
        result = SequentialExecutor().execute([case], adapter, username='tester', password='test-only')
        assert result.passed == 0
        assert result.error == 1
        assert 'expectation' in result.case_results[0].error_message.lower()
    finally:
        adapter._client._session.close()


def test_verdict_mismatch_has_explanation(mock_oj):
    adapter = LocalOJAdapter(mock_oj.base_url, timeout=1)
    case = OJCase(id='wrong-answer', desc='AC expected', problem_id='1',
                  code='// verdict:WA', expected_status='AC')
    try:
        result = SequentialExecutor().execute([case], adapter, username='tester', password='test-only')
        assert result.failed == 1
        assert 'AC' in result.case_results[0].error_message
        assert 'WA' in result.case_results[0].error_message
    finally:
        adapter._client._session.close()
