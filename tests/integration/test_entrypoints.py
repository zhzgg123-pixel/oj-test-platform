"""Public entrypoints must use the same validated configuration and fail honestly."""
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config_path(tmp_path, mock_oj):
    path = tmp_path / 'app.yaml'
    path.write_text(json.dumps({'oj': {'base_url': mock_oj.base_url, 'timeout': 2},
        'test': {'db_path': str(tmp_path / 'history.db'), 'report_dir': str(tmp_path / 'reports'), 'case_strategies': ['random'], 'generate_case_count': 1}}),
        encoding='utf-8')
    return path


def test_resources_follow_application_lifespan(config_path):
    app = create_app(config_path=str(config_path))
    assert not hasattr(app.state, 'task_manager')
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200
        assert app.state.app_config.oj.timeout == 2
        assert app.state.app_config.test.generate_case_count == 1
    assert app.state.task_manager.closed is True


def test_import_has_no_runtime_directory_side_effects(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', 'import main; import backend.app'],
                             cwd=tmp_path, env=env, capture_output=True, timeout=15)
    assert result.returncode == 0
    assert not (tmp_path / 'reports').exists()


@pytest.mark.parametrize('overrides', [
    {'strategies': []}, {'strategies': ['unknown']}, {'case_count': 0},
    {'poll_timeout': 0}, {'mode': 'concurrent', 'max_workers': 17},
])
def test_api_rejects_invalid_tasks_before_network(config_path, mock_oj, overrides):
    app = create_app(config_path=str(config_path))
    with TestClient(app) as client:
        payload = {'base_url': mock_oj.base_url, 'username': 'tester', 'password': 'do-not-echo-me'}
        payload.update(overrides)
        response = client.post('/api/tasks', json=payload)
        assert response.status_code == 422
        assert 'do-not-echo-me' not in response.text
    assert not mock_oj.requests


def test_generate_api_also_rejects_empty_strategies(config_path):
    with TestClient(create_app(config_path=str(config_path))) as client:
        assert client.post('/api/tasks/generate', json={'strategies': []}).status_code == 422


def run_cli(tmp_path, mock_oj, config_path, *arguments, password='test-only'):
    env = dict(os.environ, OJ_USERNAME='tester', OJ_PASSWORD=password, PYTHONUTF8='1')
    return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'main.py'), '--ci',
                            '--config', str(config_path), '--base-url', mock_oj.base_url, *arguments],
                           cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)


@pytest.mark.parametrize('arguments', [('--strategies',), ('--count', '0'), ('--strategies', 'unknown')])
def test_cli_invalid_config_exits_two(tmp_path, mock_oj, config_path, arguments):
    result = run_cli(tmp_path, mock_oj, config_path, *arguments)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not mock_oj.requests


def test_cli_uses_file_defaults_and_omits_password_from_output(tmp_path, mock_oj, config_path):
    output = tmp_path / 'result.json'
    result = run_cli(tmp_path, mock_oj, config_path, '--output', str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text(encoding='utf-8'))
    assert data['result']['total'] == 1
    assert data['result']['passed'] == 1
    assert 'password' not in data['config']
    for path in (tmp_path / 'reports').rglob('*'):
        if not path.is_file():
            continue
        assert 'test-only' not in path.read_text(encoding='utf-8')


def test_cli_login_failure_is_nonzero(tmp_path, mock_oj, config_path):
    result = run_cli(tmp_path, mock_oj, config_path, password='invalid')
    assert result.returncode == 1
    assert 'CI passed' not in result.stdout


def test_zero_result_cannot_get_success_exit_code():
    from main import cli_exit_code
    from core_engine.executor.base_executor import TaskResult
    assert cli_exit_code(TaskResult()) == 1
    assert cli_exit_code(TaskResult(total=1, passed=0)) == 1
    assert cli_exit_code(TaskResult(total=1, passed=1)) == 0


def test_web_task_uses_defaults_and_downloads_report(config_path, mock_oj):
    from tests.helpers import wait_until
    app = create_app(config_path=str(config_path))
    with TestClient(app) as client:
        response = client.post('/api/tasks', json={'username': 'tester', 'password': 'test-only', 'name': 'smoke'})
        assert response.status_code == 202
        task_id = response.json()['task_id']
        wait_until(lambda: app.state.task_manager.get_task(task_id).status.value in {'COMPLETED', 'FAILED'})
        task = client.get(f'/api/tasks/{task_id}').json()['task']
        assert task['result']['passed'] == 1
        assert task['name'] == 'smoke'
        assert 'test-only' not in json.dumps(task)
        report = Path(task['result']['report_paths']['json']).name
        assert client.get('/reports/' + report).status_code == 200


def test_reload_uses_same_file_and_keeps_good_config_on_error(config_path):
    with TestClient(create_app(config_path=str(config_path))) as client:
        values = json.loads(config_path.read_text(encoding='utf-8'))
        values['oj']['timeout'] = 7
        config_path.write_text(json.dumps(values), encoding='utf-8')
        assert client.post('/api/config/reload').status_code == 200
        assert client.get('/api/config').json()['config']['oj']['timeout'] == 7
        values['oj']['timeout'] = -1
        config_path.write_text(json.dumps(values), encoding='utf-8')
        assert client.post('/api/config/reload').status_code == 422
        assert client.get('/api/config').json()['config']['oj']['timeout'] == 7


def test_cli_reads_target_url_from_file(tmp_path, config_path, mock_oj):
    env = dict(os.environ, OJ_USERNAME='tester', OJ_PASSWORD='test-only', PYTHONUTF8='1')
    env.pop('OJ_BASE_URL', None)
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'main.py'), '--ci',
                            '--config', str(config_path)], cwd=tmp_path, env=env,
                           capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr
    assert len([r for r in mock_oj.requests if r['path'].startswith('/api/submit/')]) == 1
