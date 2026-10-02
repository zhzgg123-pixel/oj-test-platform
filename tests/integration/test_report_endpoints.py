import json
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app

from config_center.models import TaskConfig, ExecutionCredentials
from storage.repository import TaskRepository
from task_center.service import TaskService


def test_durable_report_contains_saved_inputs_and_version_context(tmp_path, mock_oj):
    repo = TaskRepository(tmp_path / 'tasks.db')
    service = TaskService(repo, report_root=tmp_path / 'reports')
    service.start()
    try:
        task_id = service.create(TaskConfig(base_url=mock_oj.base_url, case_count=3, seed=917),
                                 ExecutionCredentials(username='tester', password='test-only'))
        task = service.wait(task_id, 10)
        assert task.state == 'COMPLETED'
        saved = repo.list_cases(task_id)
        data = json.loads(service.report_path(task_id, 'json').read_text(encoding='utf-8'))
        assert data['task']['id'] == task_id
        assert data['task']['profile'] == task.profile
        assert data['task']['platform_sha'] == task.platform_sha
        assert data['task']['sut_sha'] is None
        assert data['config']['seed'] == 917
        for reported, original in zip(data['all_cases'], saved, strict=True):
            assert reported['stored_case_id'] == original.id
            assert reported['ordinal'] == original.ordinal
            assert reported['input']['code'] == original.input['code']
            assert reported['input']['source_sha256'] == original.source_sha256
            assert reported['expectation'] == original.expectation
            assert reported['observation'] == original.result['actual']
        html = service.report_path(task_id, 'html').read_text(encoding='utf-8')
        assert task_id in html and task.platform_sha in html
        assert 'test-only' not in html
    finally:
        service.close()


@pytest.mark.parametrize('format,media_type', [('json', 'application/json'), ('html', 'text/html')])
def test_download_integrity_missing_and_path_boundary(tmp_path, mock_oj, format, media_type):
    settings = tmp_path / 'app.yaml'
    settings.write_text(json.dumps({'test': {'db_path': str(tmp_path / 'tasks.db'),
                                           'report_dir': str(tmp_path / 'reports')}}), encoding='utf-8')
    app = create_app(config_path=settings)
    with TestClient(app) as client:
        service = app.state.task_service
        task_id = service.create(TaskConfig(base_url=mock_oj.base_url, case_count=3),
                                 ExecutionCredentials(username='tester', password='test-only'))
        assert service.wait(task_id, 10).state == 'COMPLETED'
        path = service.report_path(task_id, format)
        original = path.read_bytes()
        urls = [f'/api/v1/tasks/{task_id}/reports/{format}', f'/reports/{task_id}.{format}',
                f'/api/reports/{task_id}.{format}']
        for url in urls:
            response = client.get(url)
            assert response.status_code == 200
            assert response.content == original
            assert response.headers['content-type'].startswith(media_type)
        path.write_bytes(b'corrupt')
        for url in urls:
            assert client.get(url).status_code == 422
        listed = client.get('/api/reports').json()['reports']
        assert next(r for r in listed if r.get('task_id') == task_id and r['format'] == format)['available'] is False
        path.unlink()
        for url in urls:
            assert client.get(url).status_code == 404
        outside = tmp_path / f'outside.{format}'
        outside.write_text('outside-must-not-be-served', encoding='utf-8')
        with service.repo.database.connection(write=True) as db:
            db.execute('UPDATE reports SET relative_path=? WHERE task_id=? AND format=?',
                       (f'../outside.{format}', task_id, format))
        for url in urls:
            response = client.get(url)
            assert response.status_code == 422
            assert 'outside-must-not-be-served' not in response.text
        assert client.get(f'/api/v1/tasks/{task_id}/reports/pdf').status_code == 422


def test_second_report_registration_failure_rolls_back_pair(tmp_path, mock_oj):
    repo = TaskRepository(tmp_path / 'tasks.db')
    service = TaskService(repo, report_root=tmp_path / 'reports')
    service.start()
    try:
        with repo.database.connection(write=True) as db:
            db.execute("CREATE TRIGGER reject_html BEFORE INSERT ON reports WHEN NEW.format='html' BEGIN SELECT RAISE(ABORT, 'injected'); END")
        task_id = service.create(TaskConfig(base_url=mock_oj.base_url, case_count=3),
                                 ExecutionCredentials(username='tester', password='test-only'))
        task = service.wait(task_id, 10)
        assert task.state == 'FAILED' and task.error['stage'] == 'report'
        assert task.counts['passed'] == 3
        assert repo.list_reports(task_id) == []
        assert not list((tmp_path / 'reports').rglob('*.json'))
        assert not list((tmp_path / 'reports').rglob('*.html'))
    finally:
        service.close()
