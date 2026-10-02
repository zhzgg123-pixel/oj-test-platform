"""Durable service lifecycle against the real HTTP Mock server."""
import sqlite3

import pytest

from config_center.models import TaskConfig, ExecutionCredentials
from plugins.local_oj.adapter import LocalOJAdapter
from storage.repository import TaskRepository
from tests.helpers import wait_until

pytestmark = pytest.mark.integration


@pytest.fixture
def service(tmp_path):
    from task_center.service import TaskService
    service = TaskService(TaskRepository(tmp_path / 'tasks.db'), report_root=tmp_path / 'reports')
    service.start()
    try:
        yield service
    finally:
        service.close(timeout=10)


def config(mock_oj, count=3):
    return TaskConfig(base_url=mock_oj.base_url, case_count=count, request_timeout=2)


def credentials(password='test-only'):
    return ExecutionCredentials(username='tester', password=password)


def test_service_persists_results_and_credentials_never_enter_database(service, mock_oj):
    task_id = service.create(config(mock_oj), credentials())
    task = service.wait(task_id, timeout=10)
    assert task.state == 'COMPLETED'
    assert task.counts['passed'] == task.counts['total'] == 3
    assert service.success(task_id)
    reopened = TaskRepository(service.repo.db_path)
    assert reopened.get_task(task_id) == task
    cases = reopened.list_cases(task_id)
    assert all(c.result and c.result['attempt_count'] == 1 for c in cases)
    assert reopened.get_report(task_id, 'json')['task_id'] == task_id
    assert reopened.get_report(task_id, 'html')['task_id'] == task_id
    assert service._credentials == {}
    with sqlite3.connect(service.repo.db_path) as db:
        dump = '\n'.join(db.iterdump())
    assert 'test-only' not in dump and 'session_id' not in dump


def test_all_inputs_exist_before_adapter_creation(tmp_path, mock_oj):
    from task_center.service import TaskService
    repo = TaskRepository(tmp_path / 'tasks.db')
    captured = []
    def factory(name, base_url, timeout):
        tasks = repo.list_tasks()
        assert len(tasks) == 1
        cases = repo.list_cases(tasks[0].id)
        assert len(cases) == 3 and all(case.input['code'] for case in cases)
        captured.extend(cases)
        return LocalOJAdapter(base_url, timeout)
    service = TaskService(repo, adapter_factory=factory, report_root=tmp_path / 'reports')
    service.start()
    try:
        task_id = service.create(config(mock_oj), credentials())
        assert service.wait(task_id, 10).state == 'COMPLETED'
        assert len(captured) == 3
    finally:
        service.close()


def test_persistence_failure_never_logs_in(service, mock_oj):
    with sqlite3.connect(service.repo.db_path) as db:
        db.execute("CREATE TRIGGER reject_task BEFORE INSERT ON tasks BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        service.create(config(mock_oj), credentials())
    assert not mock_oj.requests
    assert service.repo.list_tasks() == []
    assert service._credentials == {}


def test_login_failure_is_failed_task_and_zero_submission_attempts(service, mock_oj):
    task_id = service.create(config(mock_oj), credentials('wrong-secret'))
    task = service.wait(task_id, 10)
    assert task.state == 'FAILED' and task.error['reason'] == 'LOGIN_FAILED'
    assert task.counts['error'] == task.counts['total'] == 3
    assert all(c.result['attempt_count'] == 0 for c in service.repo.list_cases(task_id))
    assert not service.success(task_id)
    assert not any('/submit/' in r['path'] for r in mock_oj.requests)
    assert service._credentials == {}


def test_failed_assertions_are_completed_execution_not_success(service, mock_oj_factory):
    mock = mock_oj_factory(response_override={'success': True, 'result': 'WA', 'passed': 0, 'total': 1, 'time_ms': 1, 'memory_kb': 1})
    cfg = TaskConfig(base_url=mock.base_url, strategies=['random'], case_count=1, seed=42)
    task_id = service.create(cfg, credentials())
    task = service.wait(task_id, 10)
    assert task.state == 'COMPLETED' and task.counts['failed'] == 1
    assert not service.success(task_id)


def test_report_failure_is_failed_task_preserving_case_results(service, mock_oj, monkeypatch):
    def fail(task_id):
        raise OSError('report failure')
    monkeypatch.setattr(service, '_write_reports', fail)
    task_id = service.create(config(mock_oj), credentials())
    task = service.wait(task_id, 10)
    assert task.state == 'FAILED' and task.error['stage'] == 'report'
    assert task.counts['passed'] == 3
    assert not service.success(task_id)


def test_bounded_queue_has_only_one_running_task_and_can_cancel_pending(service, mock_oj):
    from task_center.service import QueueFullError
    mock_oj.block_submissions()
    first = service.create(config(mock_oj), credentials())
    wait_until(lambda: mock_oj.max_active_submissions >= 1, timeout=5)
    try:
        waiting = [service.create(config(mock_oj), credentials()) for _ in range(20)]
        with pytest.raises(QueueFullError):
            service.create(config(mock_oj), credentials())
        assert service.get(first).state == 'RUNNING'
        assert all(service.get(task_id).state == 'PENDING' for task_id in waiting)
        service.cancel(waiting[0])
        assert service.get(waiting[0]).state == 'CANCELLED'
        assert service.get(waiting[0]).counts['cancelled'] == 3
        for task_id in waiting[1:]:
            service.cancel(task_id)
    finally:
        mock_oj.release_submissions()
    assert service.wait(first, 10).state == 'COMPLETED'


def test_running_cancel_stops_next_submission_and_preserves_inflight_result(service, mock_oj):
    mock_oj.block_submissions()
    task_id = service.create(config(mock_oj), credentials())
    wait_until(lambda: mock_oj.max_active_submissions >= 1, timeout=5)
    service.cancel(task_id)
    assert service.get(task_id).state == 'CANCEL_REQUESTED'
    mock_oj.release_submissions()
    task = service.wait(task_id, 10)
    assert task.state == 'CANCELLED'
    assert task.counts['passed'] == 1 and task.counts['cancelled'] == 2
    assert len([r for r in mock_oj.requests if '/submit/' in r['path']]) == 1

def test_close_timeout_retains_execution_lock_until_worker_stops(service, mock_oj):
    from task_center.runtime import ExecutionLease, RuntimeBusyError
    mock_oj.block_submissions()
    task_id = service.create(config(mock_oj), credentials())
    wait_until(lambda: mock_oj.max_active_submissions >= 1, timeout=5)
    try:
        with pytest.raises(TimeoutError, match='lock retained'):
            service.close(timeout=0)
        with pytest.raises(RuntimeBusyError):
            ExecutionLease(service.repo).start()
    finally:
        mock_oj.release_submissions()
    assert service.wait(task_id, 10).state == 'CANCELLED'
    service.close()
    next_owner = ExecutionLease(service.repo)
    next_owner.start(); next_owner.close()


def test_result_write_failure_stops_further_submissions(service, mock_oj, monkeypatch):
    def fail(*args):
        raise sqlite3.OperationalError('injected result persistence failure')
    monkeypatch.setattr(service.repo, 'save_case_result', fail)
    task_id = service.create(config(mock_oj), credentials())
    task = service.wait(task_id, 10)
    assert task.state == 'FAILED' and task.error['stage'] == 'execute'
    assert task.counts['error'] == 3
    assert len([r for r in mock_oj.requests if '/submit/' in r['path']]) == 1


def test_queued_execution_uses_stored_profile_snapshot(tmp_path, mock_oj):
    import shutil
    from config_center.profile_loader import ProfileLoader
    from task_center.service import TaskService
    profiles = tmp_path / 'profiles'
    shutil.copytree(ProfileLoader().root, profiles)
    service = TaskService(TaskRepository(tmp_path / 'tasks.db'), profile_loader=ProfileLoader(profiles),
                          report_root=tmp_path / 'reports')
    mock_oj.block_submissions()
    service.start()
    try:
        first = service.create(config(mock_oj), credentials())
        wait_until(lambda: mock_oj.max_active_submissions >= 1, timeout=5)
        queued = service.create(config(mock_oj), credentials())
        before = service.repo.list_cases(queued)
        (profiles / 'a_plus_b.yaml').write_text('invalid: profile', encoding='utf-8')
        mock_oj.release_submissions()
        service.wait(first, 10)
        assert service.wait(queued, 10).counts['passed'] == 3
        assert [c.source_sha256 for c in service.repo.list_cases(queued)] == [c.source_sha256 for c in before]
    finally:
        mock_oj.release_submissions()
        service.close()


def test_missing_or_changed_report_prevents_success(service, mock_oj):
    task_id = service.create(config(mock_oj), credentials())
    service.wait(task_id, 10)
    report = service.repo.get_report(task_id, 'json')
    path = service.report_root / report['relative_path']
    path.write_text('{}', encoding='utf-8')
    assert not service.success(task_id)
    path.unlink()
    assert not service.success(task_id)

def test_report_failure_does_not_overwrite_accepted_cancellation(service, mock_oj, monkeypatch):
    def fail(task_id):
        raise OSError('report failure during cancellation')
    monkeypatch.setattr(service, '_write_reports', fail)
    mock_oj.block_submissions()
    task_id = service.create(config(mock_oj), credentials())
    wait_until(lambda: mock_oj.max_active_submissions >= 1, timeout=5)
    try:
        service.cancel(task_id)
    finally:
        mock_oj.release_submissions()
    task = service.wait(task_id, 10)
    assert task.state == 'CANCELLED'
    assert task.error['stage'] == 'report'
    assert task.counts['passed'] == 1 and task.counts['cancelled'] == 2
