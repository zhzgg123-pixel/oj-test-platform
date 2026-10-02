"""Bounded scheduling and session isolation verified against real HTTP."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from fastapi.testclient import TestClient
import pytest

from config_center.models import TaskConfig, ExecutionCredentials
from core_engine.case_engine.case_builder import CaseBuilder
from core_engine.executor.concurrent_executor import ConcurrentExecutor
from plugins.plugin_manager import PluginManager
from storage.repository import TaskRepository
from task_center.service import TaskService
from tests.helpers import wait_until

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_factory_does_not_cache_sessions(mock_oj):
    manager = PluginManager()
    adapters = [manager.create_adapter('local_oj', mock_oj.base_url, 2) for _ in range(2)]
    try:
        assert adapters[0] is not adapters[1]
        assert adapters[0]._client is not adapters[1]._client
    finally:
        for adapter in adapters:
            adapter.close()
    legacy = [manager.create_instance('local_oj', mock_oj.base_url, 2) for _ in range(2)]
    try:
        assert legacy[0] is not legacy[1]
    finally:
        for adapter in legacy:
            adapter.close()


def test_scheduler_bounds_futures_and_isolates_sessions(mock_oj, monkeypatch):
    import core_engine.executor.concurrent_executor as module
    config = TaskConfig(base_url=mock_oj.base_url, strategies=['random'], case_count=12)
    cases = CaseBuilder().build(config)
    submitted = []
    class TrackedPool(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            future = super().submit(fn, *args, **kwargs)
            submitted.append(future)
            return future
    monkeypatch.setattr(module, 'ThreadPoolExecutor', TrackedPool)
    manager = PluginManager()
    mock_oj.block_submissions()
    executor = ConcurrentExecutor(max_workers=3)
    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(executor.execute, cases, adapter_factory=lambda: manager.create_adapter('local_oj', mock_oj.base_url, 2),
                               username='tester', password='test-only')
        try:
            wait_until(lambda: mock_oj.max_active_submissions == 3 or future.done(), timeout=5)
            if future.done():
                future.result()
            assert mock_oj.max_active_submissions == 3
            assert len(submitted) == 3  # Worker count alone must not hide an unbounded future queue.
        finally:
            mock_oj.release_submissions()
        result = future.result(timeout=10)
    assert result.passed == result.total == 12
    assert [r.case.id for r in result.case_results] == [c.id for c in cases]
    assert all(r.actual_status == r.case.expected_status for r in result.case_results)
    fingerprints = [r['session_fingerprint'] for r in mock_oj.requests if '/submit/' in r['path']]
    assert len(set(fingerprints)) == 12  # This implementation gives each case worker a fresh session.
    assert mock_oj.max_active_submissions <= 3


def test_concurrent_service_uses_per_worker_sessions_and_anonymous_request(tmp_path, mock_oj):
    service = TaskService(TaskRepository(tmp_path / 'tasks.db'), report_root=tmp_path / 'reports')
    service.start()
    mock_oj.block_submissions()
    try:
        config = TaskConfig(base_url=mock_oj.base_url, mode='concurrent', max_workers=3, case_count=9, request_timeout=3)
        task_id = service.create(config, ExecutionCredentials(username='tester', password='test-only'))
        try:
            wait_until(lambda: mock_oj.max_active_submissions >= 2, timeout=5)
            assert service.get(task_id).counts['running'] <= 3
        finally:
            mock_oj.release_submissions()
        task = service.wait(task_id, 10)
        assert task.state == 'COMPLETED' and task.counts['passed'] == 9
        requests = [r for r in mock_oj.requests if '/submit/' in r['path']]
        assert len(requests) == 9 and sum(not r['cookie_present'] for r in requests) == 1
        assert len({r['session_fingerprint'] for r in requests if r['cookie_present']}) == 8
        assert service.success(task_id)
    finally:
        mock_oj.release_submissions()
        service.close()


def test_worker_login_failure_marks_task_failed_and_stops_refill(tmp_path, mock_oj):
    service = TaskService(TaskRepository(tmp_path / 'tasks.db'), report_root=tmp_path / 'reports')
    service.start()
    try:
        cfg = TaskConfig(base_url=mock_oj.base_url, mode='concurrent', max_workers=2, strategies=['random'], case_count=10)
        task_id = service.create(cfg, ExecutionCredentials(username='tester', password='bad'))
        task = service.wait(task_id, 10)
        assert task.state == 'FAILED' and task.error['reason'] == 'LOGIN_FAILED'
        assert task.counts['error'] == 10
        assert all(c.result['attempt_count'] == 0 for c in service.repo.list_cases(task_id))
        assert len(mock_oj.requests) <= 2
        assert not any('/submit/' in r['path'] for r in mock_oj.requests)
    finally:
        service.close()


def test_public_api_and_cli_accept_concurrent_mode(tmp_path, mock_oj):
    from backend.app import create_app
    settings = tmp_path / 'app.yaml'
    settings.write_text(json.dumps({'oj': {'base_url': mock_oj.base_url, 'timeout': 2},
        'test': {'db_path': str(tmp_path / 'tasks.db'), 'report_dir': str(tmp_path / 'reports')}}), encoding='utf-8')
    with TestClient(create_app(config_path=settings)) as client:
        response = client.post('/api/v1/tasks', json={'mode': 'concurrent', 'max_workers': 3, 'case_count': 9,
                                                    'username': 'tester', 'password': 'test-only'})
        assert response.status_code == 202, response.text
        task_id = response.json()['task_id']
        wait_until(lambda: client.get(f'/api/v1/tasks/{task_id}').json()['task']['state'] in {'COMPLETED', 'FAILED'}, timeout=10)
        assert client.get(f'/api/v1/tasks/{task_id}').json()['task']['success']
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'main.py'), '--ci', '--config', str(settings),
                             '--mode', 'concurrent', '--max-workers', '3', '--case-count', '9'], cwd=tmp_path,
                            env=dict(os.environ, OJ_USERNAME='tester', OJ_PASSWORD='test-only'),
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr

def test_mixed_results_remain_bound_to_sources_when_completions_reorder(mock_oj_factory):
    from core_engine.case_engine.base_generator import TestCase as Case
    mock = mock_oj_factory(verdict_delays={'AC': 0.25, 'WA': 0.02})
    cases = [Case(id=f'case-{verdict}', desc=verdict, problem_id='1', code=f'// verdict:{verdict}', expected_status=verdict)
             for verdict in ('AC', 'WA', 'CE', 'TLE', 'RE')]
    completion_order = []
    manager = PluginManager()
    result = ConcurrentExecutor(max_workers=5).execute(cases,
        adapter_factory=lambda: manager.create_adapter('local_oj', mock.base_url, 2),
        username='tester', password='test-only', on_case_result=lambda cr: completion_order.append(cr.case.id))
    assert completion_order[0] != 'case-AC'
    assert result.passed == 5
    assert [(r.case.id, r.actual_status) for r in result.case_results] == [(c.id, c.expected_status) for c in cases]
    assert {r['code_sha256'] for r in mock.requests if '/submit/' in r['path']} == {c.source_sha256 for c in cases}


def test_worker_closes_its_own_adapter_on_login_failure(mock_oj):
    from plugins.local_oj.adapter import LocalOJAdapter
    records = []
    guard = threading.Lock()
    class TrackedAdapter(LocalOJAdapter):
        def __init__(self):
            super().__init__(mock_oj.base_url, 2)
            self.owner = threading.get_ident()
        def close(self):
            with guard:
                records.append((self.owner, threading.get_ident()))
            super().close()
    cases = CaseBuilder().build(TaskConfig(strategies=['random'], case_count=8))
    result = ConcurrentExecutor(max_workers=2).execute(cases, adapter_factory=TrackedAdapter,
                                                     username='tester', password='wrong')
    assert 1 <= len(records) <= 2
    assert all(owner == closer for owner, closer in records)
    assert result.error == 8 and result.failure_reason == 'LOGIN_FAILED'


def test_result_callback_failure_drains_inflight_without_refill(mock_oj, monkeypatch):
    import core_engine.executor.concurrent_executor as module
    cases = CaseBuilder().build(TaskConfig(strategies=['random'], case_count=12))
    submitted = []
    class TrackedPool(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            submitted.append(future)
            return future
    monkeypatch.setattr(module, 'ThreadPoolExecutor', TrackedPool)
    def failure(cr):
        raise OSError('result store failed')
    manager = PluginManager()
    mock_oj.block_submissions()
    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(ConcurrentExecutor(max_workers=3).execute, cases,
            adapter_factory=lambda: manager.create_adapter('local_oj', mock_oj.base_url, 2),
            username='tester', password='test-only', on_case_result=failure)
        try:
            wait_until(lambda: mock_oj.max_active_submissions == 3, timeout=3)
        finally:
            mock_oj.release_submissions()
        with pytest.raises(OSError, match='result store failed'):
            future.result(timeout=10)
    assert len(submitted) == 3 and all(f.done() for f in submitted)
    assert len([r for r in mock_oj.requests if '/submit/' in r['path']]) == 3

@pytest.mark.parametrize('scenario', ['health', 'login', 'rejected', 'exception'])
def test_plugin_connection_check_closes_fresh_adapter(tmp_path, mock_oj, monkeypatch, scenario):
    from backend.app import create_app
    from plugins.local_oj.adapter import LocalOJAdapter
    settings = tmp_path / 'app.yaml'
    settings.write_text(json.dumps({'test': {'db_path': str(tmp_path / 'tasks.db'),
                                            'report_dir': str(tmp_path / 'reports')}}), encoding='utf-8')
    closed = []
    class TrackedAdapter(LocalOJAdapter):
        def close(self):
            closed.append(True)
            super().close()
        def health_check(self):
            if scenario == 'exception':
                raise RuntimeError('private-value-must-not-return')
            return super().health_check()
    app = create_app(config_path=settings)
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.plugin_manager, 'create_instance',
                            lambda **kwargs: TrackedAdapter(kwargs['base_url'], kwargs['timeout']))
        payload = {'base_url': mock_oj.base_url}
        if scenario in {'login', 'rejected'}:
            payload.update(username='tester', password='test-only' if scenario == 'login' else 'wrong')
        response = client.post('/api/plugins/test', json=payload)
        assert response.status_code == 200
        assert closed == [True]
        assert 'session_id' not in response.json()
        assert 'private-value-must-not-return' not in response.text
