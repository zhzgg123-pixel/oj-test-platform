"""Bounded futures with per-case worker-owned adapters and serialized result callbacks."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import threading
import time

from core_engine.contracts import Observation
from .base_executor import BaseExecutor, CaseResult, TaskResult
from .sequential_executor import SequentialExecutor


def unsubmitted(case, status, reason):
    now = time.time()
    return CaseResult(case=case, status=status, error_message=reason,
                      start_time=now, end_time=now, attempt_count=0)


class ConcurrentExecutor(BaseExecutor):
    def __init__(self, poll_interval=1.0, poll_timeout=60, max_workers=5):
        if type(max_workers) is not int or not 1 <= max_workers <= 16:
            raise ValueError('max_workers must be between 1 and 16')
        self.max_workers = max_workers
        self._seq = SequentialExecutor(poll_interval, poll_timeout)

    def _worker(self, case, factory, cancel, username, password, login_required):
        adapter = None
        failure = None
        cr = unsubmitted(case, 'ERROR', 'WORKER_SETUP_ERROR')
        if cancel.is_set():
            return unsubmitted(case, 'CANCELLED', 'CANCELLED_BEFORE_SUBMISSION'), None
        try:
            adapter = factory()
            if login_required and case.auth_mode != 'anonymous':
                auth = adapter.login(username, password)
                if not auth.success:
                    cr = unsubmitted(case, 'ERROR', 'LOGIN_FAILED')
                    failure = ('login', 'LOGIN_FAILED')
            if failure is None:
                if cancel.is_set():
                    cr = unsubmitted(case, 'CANCELLED', 'CANCELLED_BEFORE_SUBMISSION')
                else:
                    # This adapter is fresh and owned by this invocation, including anonymous cases.
                    cr = self._seq._execute_one(case, adapter, anonymous_isolated=True)
        except Exception:
            cr = unsubmitted(case, 'ERROR', 'WORKER_SETUP_ERROR')
            cr.observation = Observation(kind='protocol_error', error_code='WORKER_SETUP_ERROR')
            failure = ('prepare', 'WORKER_SETUP_ERROR')
        finally:
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    failure = failure or ('cleanup', 'ADAPTER_CLOSE_ERROR')
        return cr, failure

    def execute(self, cases, adapter=None, **kwargs):
        factory = kwargs.get('adapter_factory')
        if factory is None:
            if adapter is None:
                raise ValueError('adapter_factory or adapter is required')
            # Legacy callers supply a prototype, never a session to share across workers.
            factory = lambda: type(adapter)(base_url=adapter.base_url, timeout=adapter.timeout)
        cancel = kwargs.get('cancel_event') or threading.Event()
        on_start = kwargs.get('on_case_start', lambda case: None)
        on_result = kwargs.get('on_case_result', lambda result: None)
        result = TaskResult(total=len(cases), start_time=time.time())
        results = {}
        pending = {}
        cursor = 0
        abort = None
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='oj-case') as pool:
            while cursor < len(cases) or pending:
                while (cursor < len(cases) and len(pending) < self.max_workers
                       and not cancel.is_set() and not result.failure_reason and abort is None):
                    index = cursor
                    try:
                        on_start(cases[index])
                        future = pool.submit(self._worker, cases[index], factory, cancel,
                                             kwargs.get('username', ''), kwargs.get('password', ''),
                                             kwargs.get('login_required', True))
                    except Exception as exc:
                        abort = exc
                        break
                    pending[future] = index
                    cursor += 1
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    index = pending.pop(future)
                    try:
                        cr, failure = future.result()
                        results[index] = cr
                        if failure and not result.failure_reason:
                            result.failure_stage, result.failure_reason = failure
                        on_result(cr)
                    except Exception as exc:
                        # Stop refill but drain existing workers, preserving any other results
                        # that can still be saved. Never retry a submission after a DB failure.
                        abort = abort or exc
            if abort is not None:
                raise abort
            for index in range(cursor, len(cases)):
                cr = unsubmitted(cases[index], 'CANCELLED' if cancel.is_set() else 'ERROR',
                                 'CANCELLED_BEFORE_SUBMISSION' if cancel.is_set() else result.failure_reason)
                results[index] = cr
                on_result(cr)
        result.case_results = [results[index] for index in range(len(cases))]
        for cr in result.case_results:
            if cr.status == 'PASSED':
                result.passed += 1
            elif cr.status == 'FAILED':
                result.failed += 1
            elif cr.status == 'CANCELLED':
                result.cancelled += 1
            else:
                result.error += 1
        result.end_time = time.time()
        return result
