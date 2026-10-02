"""Public durable API/CLI contract, with isolated databases and HTTP Mock."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from tests.helpers import wait_until

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture
def settings(tmp_path, mock_oj):
    path = tmp_path / 'app.yaml'
    path.write_text(json.dumps({'oj': {'base_url': mock_oj.base_url, 'timeout': 2},
        'test': {'db_path': str(tmp_path / 'history.db'), 'report_dir': str(tmp_path / 'reports'),
                 'case_strategies': ['random'], 'generate_case_count': 1}}), encoding='utf-8')
    return path


def submit(client):
    response = client.post('/api/v1/tasks', json={'name': 'persistent name', 'username': 'tester', 'password': 'test-only'})
    assert response.status_code == 202, response.text
    return response.json()['task_id']


def completed(client, task_id):
    response = client.get(f'/api/v1/tasks/{task_id}')
    assert response.status_code == 200, response.text
    return response.json()['task']['state'] in {'COMPLETED', 'FAILED', 'CANCELLED'}


def test_task_history_inputs_reports_and_name_survive_app_restart(settings):
    with TestClient(create_app(config_path=settings)) as client:
        task_id = submit(client)
        wait_until(lambda: completed(client, task_id), timeout=10)
        task = client.get(f'/api/v1/tasks/{task_id}').json()['task']
        assert task['state'] == 'COMPLETED' and task['success']
        assert task['name'] == 'persistent name'
        before = client.get(f'/api/v1/tasks/{task_id}/cases').json()
        assert before['cases'][0]['input']['code']
        assert before['cases'][0]['source_sha256']
    with TestClient(create_app(config_path=settings)) as client:
        restored = client.get(f'/api/v1/tasks/{task_id}').json()['task']
        assert restored == task
        assert client.get(f'/api/v1/tasks/{task_id}/cases').json() == before
        assert client.get(f'/api/tasks/{task_id}').json()['task']['id'] == task_id
        assert client.get('/api/v1/tasks?limit=1&offset=0').json()['total'] == 1
        for format in ('json', 'html'):
            report = client.get(f'/api/v1/tasks/{task_id}/reports/{format}')
            assert report.status_code == 200
            assert client.get(f'/reports/{task_id}.{format}').content == report.content
        assert client.post(f'/api/v1/tasks/{task_id}/cancel').status_code == 409
        assert client.delete(f'/api/v1/tasks/{task_id}').status_code == 200
        assert client.get(f'/api/v1/tasks/{task_id}').status_code == 404
        assert client.get(f'/api/v1/tasks/{task_id}/reports/json').status_code == 404


def test_api_limits_missing_ids_and_active_delete(settings, mock_oj):
    mock_oj.block_submissions()
    with TestClient(create_app(config_path=settings)) as client:
        task_id = submit(client)
        try:
            assert client.delete(f'/api/v1/tasks/{task_id}').status_code == 409
            for query in ('limit=101', 'limit=0', 'offset=-1'):
                assert client.get('/api/v1/tasks?' + query).status_code == 422
            for suffix in ('', '/cases', '/reports/json'):
                assert client.get('/api/v1/tasks/missing' + suffix).status_code == 404
            assert client.post('/api/v1/tasks/missing/cancel').status_code == 404
            assert client.delete('/api/v1/tasks/missing').status_code == 404
            assert client.get(f'/api/v1/tasks/{task_id}/reports/txt').status_code == 422
        finally:
            mock_oj.release_submissions()


def run_cli(settings, tmp_path, *args):
    env = dict(os.environ, OJ_USERNAME='tester', OJ_PASSWORD='test-only', PYTHONUTF8='1')
    return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'main.py'), '--ci',
                           '--config', str(settings), *args], cwd=tmp_path, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=15)


def test_cli_same_database_conflict_then_independent_database_succeeds(settings, tmp_path, mock_oj):
    with TestClient(create_app(config_path=settings)):
        conflict = run_cli(settings, tmp_path)
        assert conflict.returncode == 2, conflict.stdout + conflict.stderr
        assert 'execution owner' in conflict.stderr
        assert not mock_oj.requests
        independent = run_cli(settings, tmp_path, '--db', str(tmp_path / 'ci.db'))
        assert independent.returncode == 0, independent.stdout + independent.stderr


def test_cli_task_is_queryable_from_web_in_next_process(settings, tmp_path):
    output = tmp_path / 'run.json'
    result = run_cli(settings, tmp_path, '--output', str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text(encoding='utf-8'))
    with TestClient(create_app(config_path=settings)) as client:
        task = client.get('/api/v1/tasks/' + data['task_id']).json()['task']
        assert task['state'] == 'COMPLETED' and task['success']
        assert task['counts']['passed'] == 1
        assert 'test-only' not in json.dumps(task)


def test_database_config_precedence_and_reload_guard(settings, tmp_path, monkeypatch):
    from config_center.config import AppConfig
    assert AppConfig.load(config_path=settings, environ={'OJ_DB': str(tmp_path / 'env.db')}).test.db_path.endswith('env.db')
    override = tmp_path / 'override.db'
    monkeypatch.setenv('OJ_DB', str(tmp_path / 'env.db'))
    with TestClient(create_app(config_path=settings, db_path=override)) as client:
        assert override.exists()
        assert not (tmp_path / 'env.db').exists()
        assert client.post('/api/config/reload').status_code == 200
    monkeypatch.delenv('OJ_DB')
    with TestClient(create_app(config_path=settings)) as client:
        value = json.loads(settings.read_text(encoding='utf-8'))
        value['test']['db_path'] = str(tmp_path / 'changed.db')
        settings.write_text(json.dumps(value), encoding='utf-8')
        assert client.post('/api/config/reload').status_code == 409


def test_schema_upgrade_preserves_v1_rows_and_adds_name(tmp_path):
    from storage.repository import TaskRepository
    database = tmp_path / 'v1.db'
    sql = (ROOT / 'storage/migrations/001_initial.sql').read_text(encoding='utf-8-sig')
    with sqlite3.connect(database) as db:
        db.executescript(sql)
        db.execute('PRAGMA user_version=1')
        db.execute('INSERT INTO tasks(id,state,config_json,profile_json,profile_sha256,platform_sha,created_at) VALUES (?,?,?,?,?,?,?)',
                   ('old', 'COMPLETED', '{}', '{}', 'hash', 'sha', 1))
    repo = TaskRepository(database)
    repo.initialize()
    assert repo.get_task('old').state == 'COMPLETED'
    assert repo.get_task('old').name == ''
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2

def test_public_queue_full_returns_429_without_extra_task(settings, mock_oj):
    mock_oj.block_submissions()
    with TestClient(create_app(config_path=settings)) as client:
        payload = {'username': 'tester', 'password': 'test-only', 'request_timeout': 30}
        first = client.post('/api/v1/tasks', json=payload).json()['task_id']
        wait_until(lambda: mock_oj.max_active_submissions >= 1, timeout=5)
        queued = []
        try:
            for _ in range(20):
                response = client.post('/api/v1/tasks', json=payload)
                assert response.status_code == 202
                queued.append(response.json()['task_id'])
            assert client.post('/api/v1/tasks', json=payload).status_code == 429
            assert client.get('/api/v1/tasks').json()['total'] == 21
        finally:
            for task_id in queued:
                client.post(f'/api/v1/tasks/{task_id}/cancel')
            mock_oj.release_submissions()
        wait_until(lambda: completed(client, first), timeout=10)


def test_report_metadata_cannot_escape_root_on_download_or_delete(settings, tmp_path):
    outside = tmp_path / 'outside.txt'
    outside.write_text('preserve', encoding='utf-8')
    with TestClient(create_app(config_path=settings)) as client:
        task_id = submit(client)
        wait_until(lambda: completed(client, task_id), timeout=10)
        with sqlite3.connect(tmp_path / 'history.db') as db:
            db.execute("UPDATE reports SET relative_path='../outside.txt' WHERE task_id=? AND format='json'", (task_id,))
        assert client.get(f'/api/v1/tasks/{task_id}/reports/json').status_code == 422
        assert client.delete(f'/api/v1/tasks/{task_id}').status_code == 422
        assert outside.read_text(encoding='utf-8') == 'preserve'


def test_old_flat_report_and_new_report_list_are_available(settings, tmp_path):
    root = tmp_path / 'reports'
    root.mkdir()
    (root / 'report_legacy.json').write_text('{"legacy": true}', encoding='utf-8')
    with TestClient(create_app(config_path=settings)) as client:
        task_id = submit(client)
        wait_until(lambda: completed(client, task_id), timeout=10)
        listing = client.get('/api/reports').json()['reports']
        assert {r['filename'] for r in listing} == {'report_legacy.json', f'{task_id}.json', f'{task_id}.html'}
        assert all('size' in row for row in listing)
        assert client.get('/api/reports/report_legacy.json').json() == {'legacy': True}

def test_legacy_task_timestamps_remain_iso_strings_for_existing_frontend(settings):
    from datetime import datetime
    with TestClient(create_app(config_path=settings)) as client:
        task_id = submit(client)
        wait_until(lambda: completed(client, task_id), timeout=10)
        task = client.get('/api/tasks').json()['tasks'][0]
        for field in ('created_at', 'updated_at'):
            assert isinstance(task[field], str)
            assert datetime.fromisoformat(task[field])
            assert len(task[field][:19]) == 19
