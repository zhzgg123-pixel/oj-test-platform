"""Legacy task facade. All execution and history delegate to TaskService."""
from config_center.models import TaskConfig
from storage.repository import TaskRepository
from task_center.models import TaskStatus
from task_center.service import TaskService


class TaskView:
    def __init__(self, service, task_id):
        self.service, self.id = service, task_id

    @property
    def status(self):
        return TaskStatus(self.service.get(self.id).state)

    @property
    def config(self):
        return TaskConfig.model_validate(self.service.get(self.id).config)

    @property
    def name(self):
        return self.service.get(self.id).name

    def to_dict(self):
        return self.service.serialize_task(self.id)


class TaskManager:
    def __init__(self, report_dir='reports', db_path='runtime/tasks.db', service=None):
        self.service = service or TaskService(TaskRepository(db_path), report_root=report_dir)
        if service is None:
            self.service.start()

    @property
    def closed(self):
        return self.service.closed

    def create_task(self, config, credentials=None, name=None):
        # Durable create also enqueues atomically. start_task remains an idempotent facade.
        task_id = self.service.create(config, credentials, name=name or '测试任务')
        return TaskView(self.service, task_id)

    def start_task(self, task_id):
        return self.get_task(task_id) is not None

    def get_task(self, task_id):
        try:
            self.service.get(task_id)
            return TaskView(self.service, task_id)
        except KeyError:
            return None

    def list_tasks(self, limit=20, offset=0):
        return [TaskView(self.service, task.id) for task in self.service.repo.list_tasks(limit, offset)]

    def cancel_task(self, task_id):
        self.service.cancel(task_id)
        return True

    def delete_task(self, task_id):
        self.service.delete(task_id)
        return True

    def close(self):
        self.service.close()
