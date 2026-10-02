import json

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
            assert reported['input']['code'] == original.input['code']
            assert reported['input']['source_sha256'] == original.source_sha256
            assert reported['expectation'] == original.expectation
            assert reported['observation'] == original.result['actual']
        html = service.report_path(task_id, 'html').read_text(encoding='utf-8')
        assert task_id in html and task.platform_sha in html
        assert 'test-only' not in html
    finally:
        service.close()
