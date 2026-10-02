"""Incorrect states and unrelated failures must never satisfy an expectation."""
import pytest

from core_engine.assertion.judge_oracle import JudgeOracle
from plugins.base_adapter import JudgeResult

pytestmark = pytest.mark.unit


def test_compile_failure_is_not_wrong_answer():
    actual = JudgeResult(status='CE', passed=0, total=2, compile_msg='syntax error')
    assert JudgeOracle().verify(actual, 'WA').passed is False


@pytest.mark.parametrize('verdict', ['AC', 'WA', 'CE', 'TLE', 'RE', 'MLE'])
def test_verdict_does_not_require_invented_resource_fields(verdict):
    assert JudgeOracle().verify(JudgeResult(status=verdict), verdict).passed is True


def test_unknown_matching_strings_are_not_valid_verdicts():
    assert JudgeOracle().verify({'status': 'mystery'}, 'mystery').passed is False


@pytest.mark.parametrize('actual,status', [
    ({'kind': 'verdict', 'verdict': 'AC', 'http_status': 200}, 'FAILED'),
    ({'kind': 'http_error', 'http_status': 401}, 'FAILED'),
    ({'kind': 'transport_error', 'error_code': 'READ_TIMEOUT'}, 'ERROR'),
    ({'kind': 'protocol_error', 'error_code': 'MISSING_VERDICT'}, 'ERROR'),
    ({'kind': 'business_error', 'http_status': 200, 'error_code': 'PROBLEM_NOT_FOUND'}, 'PASSED'),
    ({'kind': 'business_error', 'http_status': 200, 'error_code': 'CODE_REQUIRED'}, 'FAILED'),
])
def test_specific_business_expectation(actual, status):
    from core_engine.contracts import Expectation, Observation
    expected = Expectation(kind='business_error', http_status=200, error_code='PROBLEM_NOT_FOUND')
    assert JudgeOracle().evaluate(expected, Observation(**actual)).status == status


@pytest.mark.parametrize('expected', ['AC', 'WA', 'CE', 'TLE', 'RE'])
@pytest.mark.parametrize('actual', ['AC', 'WA', 'CE', 'TLE', 'RE'])
def test_verdict_matrix(expected, actual):
    from core_engine.contracts import Expectation, Observation
    result = JudgeOracle().evaluate(Expectation(kind='verdict', verdict=expected),
                                    Observation(kind='verdict', verdict=actual))
    assert result.status == ('PASSED' if expected == actual else 'FAILED')


@pytest.mark.parametrize('values', [
    {'kind': 'verdict'}, {'kind': 'verdict', 'verdict': 'ERROR'},
    {'kind': 'http_error', 'http_status': 200},
    {'kind': 'business_error', 'error_code': 'NOT_FOUND'},
    {'kind': 'business_error', 'http_status': 200},
    {'kind': 'anything'},
    {'kind': 'verdict', 'verdict': 'AC', 'error_code': 'NOT_FOUND'},
])
def test_ambiguous_expectation_is_rejected(values):
    from core_engine.contracts import Expectation
    with pytest.raises(ValueError):
        Expectation(**values)
