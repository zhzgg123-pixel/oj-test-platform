"""Shared task execution entrypoint with validation before network I/O."""
from config_center.models import TaskConfig, ExecutionCredentials
from config_center.profile_loader import ProfileLoader
from core_engine.case_engine.case_builder import CaseBuilder
from core_engine.executor.sequential_executor import SequentialExecutor
from core_engine.executor.concurrent_executor import ConcurrentExecutor
from plugins.plugin_manager import PluginManager


class TaskExecutor:
    def __init__(self, profile_loader=None):
        self._case_builder = CaseBuilder()
        self._profile_loader = profile_loader or ProfileLoader()
        self._plugin_manager = PluginManager()

    def run_task(self, task_id, config, credentials=None):
        login_required = True
        if isinstance(config, dict):
            values = dict(config)
            login_required = values.pop('login_required', True)
            credentials = credentials or ExecutionCredentials(
                username=values.pop('username', ''), password=values.pop('password', ''))
            if 'plugin' in values:
                values['adapter_name'] = values.pop('plugin')
            config = TaskConfig.model_validate(values)
        credentials = credentials or ExecutionCredentials()
        adapter_type = self._plugin_manager.get_adapter(config.adapter_name)
        if adapter_type is None:
            raise ValueError('unknown adapter')
        profile = self._profile_loader.load(config.profile_id)
        cases = self._case_builder.build(config, profile)
        if not cases:
            raise ValueError('no executable cases generated')
        if config.mode == 'concurrent':
            return ConcurrentExecutor(config.poll_interval, config.poll_timeout, config.max_workers).execute(
                cases, adapter_factory=lambda: self._plugin_manager.create_adapter(
                    config.adapter_name, config.base_url, config.request_timeout),
                username=credentials.username, password=credentials.password.get_secret_value(),
                login_required=login_required)
        # An executing task owns its connection pool; never close another task's client.
        adapter = adapter_type(base_url=config.base_url, timeout=config.request_timeout)
        try:
            return SequentialExecutor(config.poll_interval, config.poll_timeout).execute(
                cases, adapter, username=credentials.username,
                password=credentials.password.get_secret_value(), login_required=login_required)
        finally:
            adapter.close()
