"""Single-consumer task service executing only durable input snapshots."""
from collections import deque
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
                                       timeout=5, stderr=subprocess.DEVNULL, text=True).strip()
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
        adapter_type = self._plugins.get_adapter(name)
        if adapter_type is None:
            raise ValueError('unknown adapter')
        return adapter_type(base_url=base_url, timeout=timeout)

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

    def create(self, config, credentials=None):
        config = TaskConfig.model_validate(config.to_dict() if isinstance(config, TaskConfig) else config)
        if config.mode != 'sequential':
            raise ValueError('concurrent mode is not enabled until S06')
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
            task_id = self.repo.insert_task(config, profile, cases, self.platform_sha, self.sut_sha)
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
            adapter = self.adapter_factory(config.adapter_name, config.base_url, config.request_timeout)
            if any(case.auth_mode != 'anonymous' for case in cases) and not cancel_event.is_set():
                stage = 'login'
                auth = adapter.login(credentials.username, credentials.password.get_secret_value())
                if not auth.success:
                    self._fail(task_id, stage, 'LOGIN_FAILED')
                    return
            stage = 'execute'
            SequentialExecutor(config.poll_interval, config.poll_timeout).execute(
                cases, adapter, login_required=False, cancel_event=cancel_event,
                on_case_start=lambda case: self.repo.mark_case_running(task_id, case.id),
                on_case_result=lambda result: self.repo.save_case_result(task_id, result))
            stage = 'report'
            self._write_reports(task_id)
            with self._condition:
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
                                     error={'stage': stage, 'reason': reason})

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
        result.end_time = task.finished_at or max((r.end_time for r in result.case_results), default=result.start_time)
        return result

    def _write_reports(self, task_id):
        # The task UUID prevents timestamp collisions; S07 adds the full evidence schema
        # and atomic output. Both current formats are generated from persisted results.
        directory = (self.report_root / task_id).resolve()
        if not directory.is_relative_to(self.report_root):
            raise ValueError('report path escapes report root')
        info = ReportGenerator(directory).generate(self.task_result(task_id), self.get(task_id).config)
        for format in ('json', 'html'):
            path = Path(info[f'{format}_path']).resolve()
            self.repo.save_report(task_id, format, path.relative_to(self.report_root).as_posix(),
                                  hashlib.sha256(path.read_bytes()).hexdigest())

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
                self.repo.transition(task_id, {'PENDING'}, 'CANCELLED')
                # The consumer may already have taken this pending task. It will observe
                # the terminal state before using credentials or opening a connection.
                self._credentials.pop(task_id, None)
                if task_id != self._active:
                    self._events.pop(task_id, None)
            elif task.state == 'RUNNING':
                self.repo.transition(task_id, {'RUNNING'}, 'CANCEL_REQUESTED')
            self._condition.notify_all()

    def close(self, timeout=30):
        with self._condition:
            if self.closed:
                return
            self._closing = True
            for task_id in list(self._pending):
                self.cancel(task_id)
            if self._active is not None and self.get(self._active).state in ACTIVE:
                self.cancel(self._active)
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                raise TimeoutError('task shutdown deadline exceeded; execution lock retained')
        with self._condition:
            self._credentials.clear()
            self._events.clear()
            self._lease.close()
            self.closed = True
