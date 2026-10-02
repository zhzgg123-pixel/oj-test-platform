"""cpp-oj's cookie-authenticated, synchronous HTTP protocol adapter."""
from __future__ import annotations

import requests
from typing import Optional

from ..base_adapter import BaseOJAdapter, LoginResult, SubmitResult, JudgeResult
from core_engine.api_client.request_client import RequestClient
from core_engine.contracts import Observation, VERDICTS
from core_engine.redaction import safe_evidence, EVIDENCE_FIELDS


class LocalOJAdapter(BaseOJAdapter):
    BUSINESS_ERRORS = {'Problem not found': 'PROBLEM_NOT_FOUND', 'Code is required': 'CODE_REQUIRED'}
    EVIDENCE_FIELDS = EVIDENCE_FIELDS

    def __init__(self, base_url: str, timeout: float = 30):
        super().__init__(base_url, timeout)
        self._client = RequestClient(base_url=base_url, timeout=timeout)
        self._secrets = set()

    def _safe_evidence(self, data):
        return safe_evidence(data, self._secrets)

    def health_check(self) -> bool:
        try:
            return self._client.get('/').status_code == 200
        except requests.RequestException:
            return False

    def login(self, username: str, password: str) -> LoginResult:
        # Failed reauthentication must not leave an earlier logged-in cookie behind.
        self._client.clear_session()
        if password:
            self._secrets.add(password)
        try:
            response = self._client.post('/api/login', data={'username': username, 'password': password})
            if response.status_code != 200:
                return LoginResult(False, message=f'Login rejected: HTTP {response.status_code}')
            data = response.json()
            if not isinstance(data, dict) or data.get('success') is not True:
                return LoginResult(False, message='Login rejected or invalid login response')
            session = self._client.get_session_id()
            if not session:
                return LoginResult(False, message='Login response missing session cookie')
            self._secrets.add(session)
            return LoginResult(True, session_id=session)
        except (requests.RequestException, ValueError) as exc:
            return LoginResult(False, message=f'Login failed: {type(exc).__name__}')

    def _error(self, kind, code=None, http_status=None, evidence=None):
        observation = Observation(kind=kind, error_code=code, http_status=http_status, evidence=evidence or {})
        return SubmitResult(False, message=code or f'HTTP {http_status}', observation=observation)

    def submit_code(self, problem_id: str, code: str, lang: str = 'cpp') -> SubmitResult:
        try:
            response = self._client.post(f'/api/submit/{problem_id}', data={'code': code, 'lang': lang})
        except requests.Timeout:
            return self._error('transport_error', 'READ_TIMEOUT')
        except requests.ConnectionError:
            return self._error('transport_error', 'CONNECTION_ERROR')
        except requests.RequestException:
            return self._error('transport_error', 'REQUEST_ERROR')
        status = response.status_code
        if status >= 400:
            return self._error('http_error', http_status=status)
        if status != 200:
            return self._error('protocol_error', 'UNEXPECTED_HTTP_STATUS', status)
        try:
            data = response.json()
        except ValueError:
            return self._error('protocol_error', 'INVALID_JSON', status)
        if not isinstance(data, dict):
            return self._error('protocol_error', 'INVALID_RESPONSE_SHAPE', status)
        safe = self._safe_evidence(data)
        if 'success' in data and type(data['success']) is not bool:
            return self._error('protocol_error', 'INVALID_RESPONSE_SHAPE', status, safe)
        if data.get('success') is False:
            if 'result' in data:
                return self._error('protocol_error', 'CONTRADICTORY_RESPONSE', status, safe)
            error = data.get('error')
            mapped = self.BUSINESS_ERRORS.get(error) if isinstance(error, str) else None
            if mapped:
                return self._error('business_error', mapped, status, safe)
            return self._error('protocol_error', 'UNKNOWN_BUSINESS_ERROR', status, safe)
        verdict = data.get('result')
        if not verdict:
            return self._error('protocol_error', 'MISSING_VERDICT', status, safe)
        if verdict not in VERDICTS:
            return self._error('protocol_error', 'UNKNOWN_VERDICT', status, safe)
        metrics = {}
        for key in ('passed', 'total', 'time_ms', 'memory_kb'):
            value = data.get(key, 0)
            if value is None and key in ('time_ms', 'memory_kb'):
                value = 0
            if type(value) is not int or value < 0:
                return self._error('protocol_error', 'INVALID_METRICS', status, safe)
            metrics[key] = value
        if metrics['passed'] > metrics['total']:
            return self._error('protocol_error', 'INVALID_METRICS', status, safe)
        for key in ('compile_error', 'detail'):
            if data.get(key) is not None and not isinstance(data[key], str):
                return self._error('protocol_error', 'INVALID_RESPONSE_SHAPE', status, safe)
        judge = JudgeResult(status=verdict, passed=metrics['passed'], total=metrics['total'],
                            time_used_ms=metrics['time_ms'], memory_used_kb=metrics['memory_kb'],
                            compile_msg=safe.get('compile_error') or '', run_msg=safe.get('detail') or '',
                            raw_response=safe)
        return SubmitResult(True, judge_result=judge,
                            observation=Observation(kind='verdict', verdict=verdict, http_status=200, evidence=safe))

    def get_judge_result(self, submit_id: str) -> Optional[JudgeResult]:
        # There is no result-query endpoint in this synchronous OJ. Never return
        # another submission's result. Callers must consume their own receipt.
        return None

    def get_problem_list(self) -> list[dict]:
        try:
            response = self._client.get('/api/problems')
            if response.status_code != 200:
                return []
            data = response.json()
            problems = data.get('problems', []) if isinstance(data, dict) else data
            return problems if isinstance(problems, list) else []
        except (requests.RequestException, ValueError):
            return []

    def get_problem_detail(self, problem_id: str) -> Optional[dict]:
        try:
            response = self._client.get(f'/api/problems/{problem_id}')
            if response.status_code != 200:
                return None
            data = response.json()
            return data if isinstance(data, dict) else None
        except (requests.RequestException, ValueError):
            return None

    def close(self):
        self._client.clear_session()
        self._client.close()
        self._secrets.clear()
