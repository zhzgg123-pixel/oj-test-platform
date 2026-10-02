"""Single-consumer task service executing only durable input snapshots."""
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import threading
import time

from config_center.models import TaskConfig, ExecutionCredentials
from config_center.profile_loader import ProfileLoader
from core_engine.case_engine.case_builder import CaseBuilder
from core_engine.contracts import Observation
from core_engine.executor.base_executor import CaseResult, TaskResult
from core_engine.executor.sequential_executor import SequentialExecutor
from core_engine.executor.concurrent_executor import ConcurrentExecutor
from core_engine.report_engine.report_generator import ReportGenerator
from plugins.plugin_manager import PluginManager
from storage.repository import ACTIVE, TERMINAL
from .runtime import ExecutionLease


class QueueFullError(RuntimeError):
    pass


class TaskConflictError(RuntimeError):
    pass


def platform_revision():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                       cwd=Path(__file__).resolve().parents[1],
                                       timeout=5, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


class TaskService:
    def __init__(self, repo, profile_loader=None, adapter_factory=None, report_root='reports',
                 platform_sha=None, sut_sha=None):
        self.repo = repo
        self.profile_loader = profile_loader or ProfileLoader()
        self.report_root = Path(report_root).resolve()
        self.platform_sha = platform_sha if platform_sha is not None else platform_revision()
        self.sut_sha = sut_sha
        self._plugins = PluginManager()
        self.adapter_factory = adapter_factory or self._new_adapter
        self._lease = ExecutionLease(repo)
        self._condition = threading.Condition()
        self._pending = deque()
        self._credentials = {}
        self._events = {}
        self._active = None
        self._thread = None
        self._closing = False
        self._fatal = None
        self.closed = False

    def _new_adapter(self, name, base_url, timeout):
        return self._plugins.create_adapter(name, base_url, timeout)

    def start(self):
        with self._condition:
            if self.closed:
                raise RuntimeError('task service is closed')
            if self._thread is not None:
                return
            self._lease.start()
            try:
                self._thread = threading.Thread(target=self._consume, name='oj-task-consumer', daemon=True)
                self._thread.start()
            except BaseException:
                self._thread = None
                self._lease.close()
                raise

    def create(self, config, credentials=None, name=''):
        config = TaskConfig.model_validate(config.to_dict() if isinstance(config, TaskConfig) else config)
        if self._plugins.get_adapter(config.adapter_name) is None:
            raise ValueError('unknown adapter')
        credentials = credentials or ExecutionCredentials()
        if not isinstance(credentials, ExecutionCredentials):
            raise TypeError('ExecutionCredentials required')
        profile = self.profile_loader.load(config.profile_id)
        cases = CaseBuilder().build(config, profile)
        with self._condition:
            if self._thread is None or self._closing or self.closed or self._fatal:
                raise RuntimeError('task service is not accepting tasks')
            if len(self._pending) >= 20:
                raise QueueFullError('task waiting queue is full (20)')
            task_id = self.repo.insert_task(config, profile, cases, self.platform_sha, self.sut_sha, name=name)
            self._credentials[task_id] = credentials.model_copy(deep=True)
            self._events[task_id] = threading.Event()
            self._pending.append(task_id)
            self._condition.notify_all()
            return task_id

    def get(self, task_id):
        return self.repo.get_task(task_id)

    def wait(self, task_id, timeout=60):
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                task = self.get(task_id)
                if task.state in TERMINAL and task_id not in self._credentials:
                    return task
                if self._fatal:
                    raise RuntimeError('task consumer stopped after persistence failure')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('task wait deadline exceeded')
                self._condition.wait(timeout=min(remaining, 0.2))

    def _consume(self):
        while True:
            with self._condition:
                while not self._pending and not self._closing:
                    self._condition.wait()
                if self._closing:
                    return
                task_id = self._pending.popleft()
                self._active = task_id
            try:
                self._run(task_id)
            except Exception as exc:
                # A DB failure may prevent marking FAILED. Stop further requests and retain
                # ownership until close; the next owner will recover the durable active state.
                with self._condition:
                    self._fatal = type(exc).__name__
            finally:
                with self._condition:
                    self._credentials.pop(task_id, None)
                    self._events.pop(task_id, None)
                    self._active = None
                    self._condition.notify_all()
            if self._fatal:
                return

    def _run(self, task_id):
        adapter = None
        stage = 'prepare'
        try:
            with self._condition:
                if not self.repo.transition(task_id, {'PENDING'}, 'RUNNING'):
                    return
                cancel_event = self._events[task_id]
                credentials = self._credentials[task_id]
            task = self.get(task_id)
            config = TaskConfig.model_validate(task.config)
            cases = [stored.to_case() for stored in self.repo.list_cases(task_id)]
            callbacks = dict(cancel_event=cancel_event,
                             on_case_start=lambda case: self.repo.mark_case_running(task_id, case.id),
                             on_case_result=lambda result: self.repo.save_case_result(task_id, result))
            if config.mode == 'concurrent':
                stage = 'execute'
                summary = ConcurrentExecutor(config.poll_interval, config.poll_timeout, config.max_workers).execute(
                    cases, adapter_factory=lambda: self.adapter_factory(config.adapter_name, config.base_url, config.request_timeout),
                    username=credentials.username, password=credentials.password.get_secret_value(), **callbacks)
                if summary.failure_reason:
                    self._fail(task_id, summary.failure_stage, summary.failure_reason)
                    return
            else:
                adapter = self.adapter_factory(config.adapter_name, config.base_url, config.request_timeout)
                if any(case.auth_mode != 'anonymous' for case in cases) and not cancel_event.is_set():
                    stage = 'login'
                    auth = adapter.login(credentials.username, credentials.password.get_secret_value())
                    if not auth.success:
                        self._fail(task_id, stage, 'LOGIN_FAILED')
                        return
                stage = 'execute'
                SequentialExecutor(config.poll_interval, config.poll_timeout).execute(
                    cases, adapter, login_required=False, **callbacks)
            stage = 'report'
            with self._condition:
                # Publish the cancellation snapshot and terminal state together.
                self._write_reports(task_id)
                state = self.get(task_id).state
                self.repo.transition(task_id, {state}, 'CANCELLED' if state == 'CANCEL_REQUESTED' else 'COMPLETED')
        except Exception as exc:
            self._fail(task_id, stage, type(exc).__name__)
        finally:
            if adapter is not None:
                adapter.close()

    def _fail(self, task_id, stage, reason):
        with self._condition:
            state = self.get(task_id).state
            if state in ACTIVE:
                cancelled = state == 'CANCEL_REQUESTED'
                self.repo.finish_unstarted_cases(task_id, 'CANCELLED' if cancelled else 'ERROR', reason)
                self.repo.transition(task_id, {state}, 'CANCELLED' if cancelled else 'FAILED',
                                     error={**(self.get(task_id).error or {}), 'stage': stage, 'reason': reason})

    def task_result(self, task_id):
        task = self.get(task_id)
        result = TaskResult(total=task.counts['total'], passed=task.counts['passed'],
                            failed=task.counts['failed'], error=task.counts['error'],
                            cancelled=task.counts['cancelled'], start_time=task.started_at or task.created_at)
        for stored in self.repo.list_cases(task_id):
            row = stored.result
            if row is None:
                continue
            actual = Observation(**row['actual']) if row['actual'] else None
            result.case_results.append(CaseResult(
                case=stored.to_case(), status=row['assertion_status'], observation=actual,
                actual_status=(actual.verdict or actual.error_code or f'HTTP_{actual.http_status}') if actual else '',
                error_message=row['reason'], start_time=row['started_at'], end_time=row['finished_at'],
                attempt_count=row['attempt_count']))
        result.remote_execution_may_continue = bool((task.error or {}).get('remote_execution_may_continue'))
        result.end_time = task.finished_at or max((r.end_time for r in result.case_results), default=result.start_time)
        return result

    def _write_reports(self, task_id):
        # Both formats use persisted results. Publish complete files before registering
        # the pair; a crash between these systems can leave unregistered orphan files.
        directory = (self.report_root / task_id).resolve()
        if not directory.is_relative_to(self.report_root):
            raise ValueError('report path escapes report root')
        task = self.get(task_id)
        context = {key: getattr(task, key) for key in
                   ('id', 'name', 'profile', 'profile_sha256', 'platform_sha', 'sut_sha', 'created_at', 'started_at')}
        info = ReportGenerator(directory).generate(self.task_result(task_id), task.config, task_context=context)
        paths = [Path(info[f'{format}_path']).resolve() for format in ('json', 'html')]
        if any(not path.is_relative_to(directory) for path in paths):
            raise ValueError('generated report escapes task directory')
        try:
            artifacts = [dict(format=format, relative_path=path.relative_to(self.report_root).as_posix(),
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                         for format, path in zip(('json', 'html'), paths)]
            self.repo.save_reports(task_id, artifacts)
        except BaseException:
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass  # Unregistered files cannot be served through task metadata.
            raise

    def success(self, task_id):
        task = self.get(task_id)
        if task.state != 'COMPLETED' or not task.counts['total'] or task.counts['passed'] != task.counts['total']:
            return False
        for format in ('json', 'html'):
            try:
                report = self.repo.get_report(task_id, format)
                path = (self.report_root / report['relative_path']).resolve()
                if not path.is_relative_to(self.report_root) or hashlib.sha256(path.read_bytes()).hexdigest() != report['sha256']:
                    return False
            except (KeyError, OSError):
                return False
        return True

    def cancel(self, task_id):
        with self._condition:
            task = self.get(task_id)
            if task.state not in ACTIVE:
                raise TaskConflictError('task is already terminal')
            event = self._events.get(task_id)
            if event is None:
                raise TaskConflictError('task is not owned by this runtime')
            event.set()
            if task.state == 'PENDING':
                if task_id in self._pending:
                    self._pending.remove(task_id)
                self.repo.finish_unstarted_cases(task_id, 'CANCELLED', 'CANCELLED_BEFORE_SUBMISSION')
                self.repo.transition(task_id, {'PENDING'}, 'CANCELLED',
                                     error={'stage': 'cancel', 'reason': 'USER_CANCELLED',
                                            'remote_execution_may_continue': False})
                # The consumer may already have taken this pending task. It will observe
                # the terminal state before using credentials or opening a connection.
                self._credentials.pop(task_id, None)
                if task_id != self._active:
                    self._events.pop(task_id, None)
            elif task.state == 'RUNNING':
                self.repo.transition(task_id, {'RUNNING'}, 'CANCEL_REQUESTED',
                                     error={'stage': 'cancel', 'reason': 'USER_CANCELLED',
                                            'remote_execution_may_continue': True})
            self._condition.notify_all()

    def close(self, timeout=30):
        deadline = time.monotonic() + max(0, timeout)
        if not self._condition.acquire(timeout=max(0, deadline - time.monotonic())):
            raise TimeoutError('task shutdown deadline exceeded; execution lock retained')
        try:
            if self.closed:
                return
            self._closing = True
            for task_id in list(self._pending):
                self.cancel(task_id)
            if self._active is not None and self.get(self._active).state in ACTIVE:
                self.cancel(self._active)
            self._condition.notify_all()
        finally:
            self._condition.release()
        if self._thread is not None:
            self._thread.join(timeout=max(0, deadline - time.monotonic()))
            if self._thread.is_alive():
                raise TimeoutError('task shutdown deadline exceeded; execution lock retained')
        with self._condition:
            self._credentials.clear()
            self._events.clear()
            self._lease.close()
            self.closed = True

    def report_path(self, task_id, format):
        report = self.repo.get_report(task_id, format)
        path = (self.report_root / report['relative_path']).resolve()
        if not path.is_relative_to(self.report_root):
            raise ValueError('report path escapes report root')
        if not path.is_file():
            raise FileNotFoundError('report file is missing')
        if hashlib.sha256(path.read_bytes()).hexdigest() != report['sha256']:
            raise ValueError('report integrity check failed')
        return path

    def serialize_task(self, task_id):
        task = self.get(task_id)
        value = asdict(task)
        result = self.task_result(task_id)
        done = task.counts['total'] - task.counts['pending'] - task.counts['running']
        value.update(status=task.state, progress=int(100 * done / task.counts['total']) if task.counts['total'] else 0,
                     progress_desc=task.state, updated_at=task.finished_at or task.started_at or task.created_at,
                     error_message=task.error['reason'] if task.error else '', success=self.success(task_id))
        for field in ('created_at', 'started_at', 'finished_at', 'updated_at'):
            if value.get(field) is not None:
                value[field] = datetime.fromtimestamp(value[field], timezone.utc).isoformat()
        reports = self.repo.list_reports(task_id)
        value['result'] = {**task.counts, 'pass_rate': result.pass_rate, 'duration': result.duration,
                           'report_paths': {r['format']: f"reports/{task_id}.{r['format']}" for r in reports},
                           'details': [{'case_id': cr.case.id, 'description': cr.case.desc,
                                        'expected': cr.case.expected_status, 'actual': cr.actual_status,
                                        'status': cr.status, 'passed': cr.passed, 'elapsed': cr.duration}
                                       for cr in result.case_results]}
        return value

    def delete(self, task_id):
        with self._condition:
            if self.get(task_id).state in ACTIVE or self._active == task_id:
                raise TaskConflictError('cannot delete active task')
            paths = []
            for report in self.repo.list_reports(task_id):
                path = (self.report_root / report['relative_path']).resolve()
                if not path.is_relative_to(self.report_root):
                    raise ValueError('report path escapes report root')
                paths.append(path)
            for path in paths:
                path.unlink(missing_ok=True)
            self.repo.delete_task(task_id)
