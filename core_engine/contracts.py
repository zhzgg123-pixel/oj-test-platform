"""Explicit, serializable expectations and observations; no I/O or credentials."""
from dataclasses import dataclass, field
from typing import Any, Literal

VERDICTS = ('AC', 'WA', 'CE', 'TLE', 'RE', 'MLE')
ExpectationKind = Literal['verdict', 'http_error', 'business_error']
ObservationKind = Literal['verdict', 'http_error', 'business_error', 'transport_error', 'protocol_error']


def _validate(kind, verdict, http_status, error_code, *, observed):
    kinds = {'verdict', 'http_error', 'business_error'}
    if observed:
        kinds |= {'transport_error', 'protocol_error'}
    if kind not in kinds:
        raise ValueError('unknown expectation/observation kind')
    if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
        raise ValueError('invalid HTTP status')
    if kind == 'verdict':
        if verdict not in VERDICTS or error_code is not None:
            raise ValueError('verdict requires a known status and no error code')
        if http_status is not None and not 200 <= http_status < 300:
            raise ValueError('verdict cannot accompany an HTTP error')
    else:
        if verdict is not None:
            raise ValueError('non-verdict observation cannot carry a verdict')
        if kind == 'http_error':
            if http_status is None or http_status < 400 or error_code is not None:
                raise ValueError('http_error requires a 4xx/5xx status and no business code')
        else:
            if not isinstance(error_code, str) or not error_code.strip():
                raise ValueError('error code is required')
            if kind == 'business_error' and http_status is None:
                raise ValueError('business_error requires an HTTP status')


@dataclass(frozen=True)
class Expectation:
    kind: ExpectationKind
    verdict: str | None = None
    http_status: int | None = None
    error_code: str | None = None

    def __post_init__(self):
        _validate(self.kind, self.verdict, self.http_status, self.error_code, observed=False)


@dataclass(frozen=True)
class Observation:
    kind: ObservationKind
    verdict: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _validate(self.kind, self.verdict, self.http_status, self.error_code, observed=True)


@dataclass(frozen=True)
class AssertionResult:
    status: Literal['PASSED', 'FAILED', 'ERROR']
    reason: str


@dataclass(frozen=True)
class SubmissionReceipt:
    submission_id: str
    immediate_observation: Observation | None = None
