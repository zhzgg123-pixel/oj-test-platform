"""Cancellation is a scheduling action, not only a terminal label."""
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from config_center.models import TaskConfig, ExecutionCredentials
from storage.repository import TaskRepository
from task_center.runtime import ExecutionLease, RuntimeBusyError
from task_center.service import TaskService
from tests.helpers import wait_until

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture
def service(tmp_path):
    service = TaskService(TaskRepository(tmp_path / 'history.db'), report_root=tmp_path / 'reports')
    service.start()
    try:
        yield service
    finally:
        service.close(timeout=10)


def cfg(mock, mode='concurrent', timeout=3):
    return TaskConfig(base_url=mock.base_url, mode=mode, max_workers=3, strategies=['random'],
                      case_count=12, request_timeout=timeout)


def credentials():
    return ExecutionCredentials(username='tester', password='test-only')


def submissions(mock):
    return [r for r in mock.requests if '/submit/' in r['path']]


@pytest.mark.parametrize('mode,expected_inflight', [('sequential', 1), ('concurrent', 3)])
def test_cancel_stops_refill_and_preserves_inflight_results(service, mock_oj, mode, expected_inflight):
    mock_oj.block_submissions()
    task_id = service.create(cfg(mock_oj, mode), credentials())
    try:
        wait_until(lambda: mock_oj.max_active_submissions == expected_inflight, timeout=3)
        before = len(submissions(mock_oj))
        service.cancel(task_id)
        task = service.get(task_id)
        assert task.state == 'CANCEL_REQUESTED'
        assert task.counts['pending'] + task.counts['running'] == 12
    finally:
        mock_oj.release_submissions()
    task = service.wait(task_id, 10)
    assert task.state == 'CANCELLED'
    assert task.counts['passed'] == before == expected_inflight
    assert task.counts['cancelled'] == 12 - before
    assert task.counts['total'] == sum(task.counts[k] for k in ('passed', 'failed', 'error', 'cancelled'))
    assert len(submissions(mock_oj)) == before
    assert task.error['remote_execution_may_continue'] is True
    report = json.loads(service.report_path(task_id, 'json').read_text(encoding='utf-8'))
    assert report['summary']['cancelled'] == 12 - before
    assert report['remote_execution_may_continue'] is True
    assert '远端' in service.report_path(task_id, 'html').read_text(encoding='utf-8')
    assert service._credentials == {}


def test_cancel_pending_has_zero_requests_and_no_remote_execution_flag(service, mock_oj):
    mock_oj.block_submissions()
    first = service.create(cfg(mock_oj), credentials())
    try:
        wait_until(lambda: mock_oj.max_active_submissions == 3, timeout=3)
        pending = service.create(cfg(mock_oj), credentials())
        service.cancel(pending)
        task = service.get(pending)
        assert task.state == 'CANCELLED' and task.counts['cancelled'] == 12
        assert task.error['remote_execution_may_continue'] is False
        assert all(c.result['attempt_count'] == 0 for c in service.repo.list_cases(pending))
        assert pending not in service._credentials
        service.cancel(first)
    finally:
        mock_oj.release_submissions()
    service.wait(first, 10)
    assert len(submissions(mock_oj)) == 3


def test_cancel_with_request_timeout_keeps_errors_and_never_refills(service, mock_oj):
    mock_oj.block_submissions()
    task_id = service.create(cfg(mock_oj, timeout=0.4), credentials())
    try:
        wait_until(lambda: mock_oj.max_active_submissions == 3, timeout=3)
        service.cancel(task_id)
        task = service.wait(task_id, 5)
        assert task.state == 'CANCELLED'
        assert task.counts['error'] == 3 and task.counts['cancelled'] == 9
        assert len(submissions(mock_oj)) == 3
        assert task.error['remote_execution_may_continue'] is True
    finally:
        mock_oj.release_submissions()


def test_concurrent_shutdown_retains_lock_until_workers_stop(service, mock_oj):
    mock_oj.block_submissions()
    task_id = service.create(cfg(mock_oj), credentials())
    try:
        wait_until(lambda: mock_oj.max_active_submissions == 3, timeout=3)
        with pytest.raises(TimeoutError, match='lock retained'):
            service.close(timeout=0)
        with pytest.raises(RuntimeBusyError):
            ExecutionLease(service.repo).start()
    finally:
        mock_oj.release_submissions()
    assert service.wait(task_id, 10).state == 'CANCELLED'
    service.close()
    lease = ExecutionLease(service.repo)
    lease.start(); lease.close()
    assert len(submissions(mock_oj)) == 3


def test_public_cancel_returns_progress_and_keeps_final_state(tmp_path, mock_oj):
    path = tmp_path / 'app.yaml'
    path.write_text(json.dumps({'test': {'db_path': str(tmp_path / 'history.db'),
                                        'report_dir': str(tmp_path / 'reports')}}), encoding='utf-8')
    mock_oj.block_submissions()
    with TestClient(create_app(config_path=path)) as client:
        response = client.post('/api/v1/tasks', json={**cfg(mock_oj).to_dict(), 'username': 'tester', 'password': 'test-only'})
        task_id = response.json()['task_id']
        try:
            wait_until(lambda: mock_oj.max_active_submissions == 3, timeout=3)
            assert client.post(f'/api/v1/tasks/{task_id}/cancel').status_code == 200
            middle = client.get(f'/api/v1/tasks/{task_id}').json()['task']
            assert middle['state'] == 'CANCEL_REQUESTED' and middle['counts']['running'] == 3
        finally:
            mock_oj.release_submissions()
        wait_until(lambda: client.get(f'/api/v1/tasks/{task_id}').json()['task']['state'] == 'CANCELLED', timeout=5)
        task = client.get(f'/api/v1/tasks/{task_id}').json()['task']
        assert task['progress'] == 100 and not task['success']
        assert task['error']['remote_execution_may_continue'] is True
        assert client.post(f'/api/v1/tasks/{task_id}/cancel').status_code == 409


def test_cli_keyboardinterrupt_cancels_task_and_exits_130(tmp_path, mock_oj):
    # Generate a real KeyboardInterrupt on the child's main thread after parent has
    # observed the first three HTTP requests. No console-wide Windows signal is sent.
    code = '''
import _thread, sys, threading, faulthandler
faulthandler.dump_traceback_later(10)
from main import main
def interrupt():
    sys.stdin.readline()
    _thread.interrupt_main()
threading.Thread(target=interrupt, daemon=True).start()
raise SystemExit(main(sys.argv[1:]))
'''
    database = tmp_path / 'cli.db'
    mock_oj.block_submissions()
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', code, '--ci', '--base-url', mock_oj.base_url,
                                '--db', str(database), '--report-dir', str(tmp_path / 'reports'),
                                '--mode', 'concurrent', '--max-workers', '3', '--strategies', 'random',
                                '--case-count', '12', '--timeout', '3'], cwd=ROOT,
                               env=dict(os.environ, OJ_USERNAME='tester', OJ_PASSWORD='test-only'),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_until(lambda: mock_oj.max_active_submissions == 3 or process.poll() is not None, timeout=5)
        assert process.poll() is None
        repo = TaskRepository(database)
        task_id = repo.list_tasks()[0].id
        process.stdin.write(b'cancel\n'); process.stdin.flush()
        wait_until(lambda: repo.get_task(task_id).state == 'CANCEL_REQUESTED', timeout=3)
        mock_oj.release_submissions()
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130, (stdout, stderr)
        assert repo.get_task(task_id).state == 'CANCELLED'
        assert len(submissions(mock_oj)) == 3
        lease = ExecutionLease(repo); lease.start(); lease.close()
    except Exception as exc:
        if process.poll() is None:
            process.kill()
        stdout, stderr = process.communicate(timeout=10)
        raise AssertionError(f'child output: {stdout!r}; errors: {stderr!r}; requests: {mock_oj.requests!r}') from exc
    finally:
        mock_oj.release_submissions()
        if process.poll() is None:
            process.kill(); process.communicate(timeout=10)

def test_cancel_during_sequential_admission_does_not_submit(mock_oj):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from core_engine.case_engine.case_builder import CaseBuilder
    from core_engine.executor.sequential_executor import SequentialExecutor
    from plugins.local_oj.adapter import LocalOJAdapter
    cases = CaseBuilder().build(TaskConfig(strategies=['random'], case_count=1))
    cancel, entered, release = threading.Event(), threading.Event(), threading.Event()
    adapter = LocalOJAdapter(mock_oj.base_url, 2)
    def on_start(case):
        entered.set()
        assert release.wait(3)
    try:
        with ThreadPoolExecutor(max_workers=1) as caller:
            future = caller.submit(SequentialExecutor().execute, cases, adapter,
                                   username='tester', password='test-only', cancel_event=cancel, on_case_start=on_start)
            try:
                assert entered.wait(3)
                cancel.set()
            finally:
                release.set()
            result = future.result(timeout=5)
        assert not submissions(mock_oj)
        assert result.cancelled == 1 and result.case_results[0].attempt_count == 0
    finally:
        adapter.close()

def test_report_publication_and_terminal_state_are_serialized_with_cancel(service, mock_oj, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
    import threading
    from task_center.service import TaskConflictError
    entered, release, cancelling = threading.Event(), threading.Event(), threading.Event()
    original = service._write_reports
    def blocked_report(task_id):
        original(task_id)
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(service, '_write_reports', blocked_report)
    task_id = service.create(cfg(mock_oj), credentials())
    def cancel():
        cancelling.set()
        service.cancel(task_id)
    with ThreadPoolExecutor(max_workers=1) as caller:
        try:
            assert entered.wait(3)
            future = caller.submit(cancel)
            assert cancelling.wait(3)
            with pytest.raises(FutureTimeout):
                future.result(timeout=0.1)
            with pytest.raises(TimeoutError, match='lock retained'):
                service.close(timeout=0)
        finally:
            release.set()
        with pytest.raises(TaskConflictError):
            future.result(timeout=5)
    task = service.wait(task_id, 10)
    assert task.state == 'COMPLETED'
    report = json.loads(service.report_path(task_id, 'json').read_text(encoding='utf-8'))
    assert report['remote_execution_may_continue'] is False
