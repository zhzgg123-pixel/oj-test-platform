import json
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app


@pytest.mark.parametrize('mode,workers', [('sequential', 1), ('concurrent', 3)])
def test_web_creation_preserves_profile_seed_mode_and_location(tmp_path, mock_oj, mode, workers):
    app = create_app(db_path=tmp_path / 'web.db', report_dir=tmp_path / 'reports')
    with TestClient(app) as client:
        profiles = client.get('/api/v1/profiles').json()['profiles']
        assert {'a_plus_b', 'max_of_two'} <= {p['id'] for p in profiles}
        response = client.post('/api/v1/tasks', json=dict(name='web flow', base_url=mock_oj.base_url,
            username='tester', password='test-only', profile_id='max_of_two', problem_id='2',
            strategies=['random'], case_count=4, seed=917, mode=mode, max_workers=workers))
        assert response.status_code == 202
        task_id = response.json()['task_id']
        assert response.headers['location'] == f'/api/v1/tasks/{task_id}'
        app.state.task_service.wait(task_id, 10)
        detail = client.get(response.headers['location'])
        assert 'test-only' not in detail.text
        config = detail.json()['task']['config']
        assert config['profile_id'] == 'max_of_two' and config['seed'] == 917
        assert config['mode'] == mode and config['max_workers'] == workers
        assert client.post(f'/api/v1/tasks/{task_id}/cancel').status_code == 409
