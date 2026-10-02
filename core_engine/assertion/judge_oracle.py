"""Single assertion authority: unrelated errors never satisfy a business expectation."""
from dataclasses import dataclass
from typing import Callable

from core_engine.contracts import AssertionResult, Expectation, Observation, VERDICTS


@dataclass
class OracleResult:
    """Compatibility result for existing verify() callers."""
    passed: bool
    expected: str
    actual: str
    detail: str = ''

    def to_dict(self):
        return vars(self).copy()


class JudgeOracle:
    # Optional checks may narrow a verdict match, never turn a mismatch into a pass.
    RULES: dict[str, dict] = {}

    def evaluate(self, expected: Expectation, observed: Observation) -> AssertionResult:
        if observed.kind in {'transport_error', 'protocol_error'}:
            return AssertionResult('ERROR', f'{observed.kind}: {observed.error_code}')
        matched = expected.kind == observed.kind
        if expected.kind == 'verdict':
            matched = matched and expected.verdict == observed.verdict
        elif expected.kind == 'http_error':
            matched = matched and expected.http_status == observed.http_status
        else:
            matched = (matched and expected.http_status == observed.http_status
                       and expected.error_code == observed.error_code)
        reason = (f'expected {expected.kind}:{expected.verdict or expected.error_code or expected.http_status}; '
                  f'actual {observed.kind}:{observed.verdict or observed.error_code or observed.http_status}')
        if matched and expected.kind == 'verdict' and expected.verdict in self.RULES:
            rule = self.RULES[expected.verdict]
            try:
                matched = bool(rule['check'](dict(observed.evidence, status=observed.verdict)))
                reason += f'; additional check: {rule["desc"]}'
            except Exception:
                return AssertionResult('ERROR', 'additional verdict check failed to execute')
        return AssertionResult('PASSED' if matched else 'FAILED', reason)

    def verify(self, judge_result, expected_status: str) -> OracleResult:
        data = judge_result if isinstance(judge_result, dict) else vars(judge_result)
        actual = data.get('status', data.get('result', 'UNKNOWN'))
        try:
            result = self.evaluate(Expectation(kind='verdict', verdict=expected_status),
                                   Observation(kind='verdict', verdict=actual, evidence=data))
        except (ValueError, TypeError):
            return OracleResult(False, expected_status, str(actual), 'invalid expectation or observed verdict')
        return OracleResult(result.status == 'PASSED', expected_status, actual, result.reason)

    @classmethod
    def register_rule(cls, status: str, check_func: Callable, desc: str = ''):
        if status not in VERDICTS or not callable(check_func):
            raise ValueError('additional check requires a supported verdict and callable')
        cls.RULES[status] = {'check': check_func, 'desc': desc}

    @classmethod
    def get_supported_statuses(cls):
        return list(VERDICTS)
