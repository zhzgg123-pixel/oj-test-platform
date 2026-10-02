import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from config_center.models import TaskConfig, ExecutionCredentials
from core_engine.executor.task_executor import TaskExecutor

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('profile_id,problem_id', [('a_plus_b', '1'), ('max_of_two', '2')])
def test_all_three_strategies_use_one_execution_flow(mock_oj, profile_id, problem_id):
    config = TaskConfig(profile_id=profile_id, problem_id=problem_id, base_url=mock_oj.base_url, case_count=9)
    result = TaskExecutor().run_task('profile-task', config,
                                    ExecutionCredentials(username='tester', password='test-only'))
    assert result.total == 9
    assert result.passed == 9
    assert result.failed == result.error == 0
    submits = [r for r in mock_oj.requests if r['path'].startswith('/api/submit/')]
    assert len(submits) == 9
    assert sum(not r['cookie_present'] for r in submits) == 1
    assert result.case_results[2].observation.http_status == 401


def test_unknown_profile_fails_before_login(mock_oj):
    config = TaskConfig(profile_id='absent', base_url=mock_oj.base_url)
    with pytest.raises(ValueError):
        TaskExecutor().run_task('missing-profile', config, ExecutionCredentials())
    assert not mock_oj.requests


def test_profile_list_and_generation_api(tmp_path, mock_oj):
    path = tmp_path / 'app.yaml'
    path.write_text(json.dumps({'oj': {'base_url': mock_oj.base_url},
                                'test': {'db_path': str(tmp_path / 'history.db'), 'report_dir': str(tmp_path / 'reports')}}), encoding='utf-8')
    with TestClient(create_app(config_path=path)) as client:
        listing = client.get('/api/v1/profiles')
        assert listing.status_code == 200
        assert {p['id'] for p in listing.json()['profiles']} == {'a_plus_b', 'max_of_two'}
        generated = client.post('/api/tasks/generate', json={
            'profile_id': 'max_of_two', 'problem_id': '2', 'strategies': ['random'], 'case_count': 1})
        assert generated.status_code == 200
        case = generated.json()['cases'][0]
        assert case['profile_id'] == 'max_of_two'
        assert case['seed'] == 42
        assert case['source_code'] and case['source_sha256']
        assert client.post('/api/tasks', json={'profile_id': 'missing'}).status_code == 422


def test_anonymous_only_rule_does_not_require_login(mock_oj):
    config = TaskConfig(base_url=mock_oj.base_url, strategies=['rule'], case_count=1)
    result = TaskExecutor().run_task('anonymous', config, ExecutionCredentials(password='wrong'))
    assert result.passed == 1
    assert [r['path'] for r in mock_oj.requests] == ['/api/submit/1']


def test_cli_selects_second_profile_and_generates_exact_total(tmp_path, mock_oj):
    from config_center.profile_loader import ProfileLoader
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, OJ_USERNAME='tester', OJ_PASSWORD='test-only', PYTHONUTF8='1')
    output = tmp_path / 'result.json'
    result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'main.py'), '--ci',
        '--base-url', mock_oj.base_url, '--profile', 'max_of_two', '--problem-id', '2',
        '--case-count', '9', '--output', str(output), '--report-dir', str(tmp_path / 'reports')],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text(encoding='utf-8'))
    assert data['config']['profile_id'] == 'max_of_two'
    assert data['result']['total'] == data['result']['passed'] == 9
    first_submit = next(r for r in mock_oj.requests if r['path'].startswith('/api/submit/'))
    assert first_submit['code_sha256'] == ProfileLoader().load('max_of_two').source_hashes['templates/max_of_two/ac.cpp']
