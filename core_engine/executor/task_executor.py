"""
任务执行器 - TaskExecutor

文档规范：
- 整合 CaseBuilder + SequentialExecutor
- run_task(task_id, config) -> TaskResult
- 负责 adapter 创建、用例生成、执行调度

可选增强：
- 多 adapter 并发
- 结果回调
"""

from __future__ import annotations
import logging
from typing import Optional

from core_engine.executor.base_executor import TaskResult
from core_engine.executor.sequential_executor import SequentialExecutor
from core_engine.case_engine.case_builder import CaseBuilder
from plugins.plugin_manager import PluginManager

logger = logging.getLogger("oj.task_executor")


class TaskExecutor:
    """任务级执行器 - 整合用例生成 + 执行 + 结果汇总"""

    def __init__(self):
        self._case_builder = CaseBuilder()
        self._plugin_manager = PluginManager()

    def run_task(self, task_id: str, config: dict) -> TaskResult:
        """
        运行一个完整测试任务

        Args:
            task_id: 任务 ID
            config: 任务配置
                - plugin: 适配器名称 (default: local_oj)
                - base_url: OJ 地址
                - problem_id: 题目 ID
                - strategies: 生成策略
                - case_count: 用例数量
                - username/password: 登录信息
                - poll_interval/poll_timeout: 轮询参数

        Returns:
            TaskResult
        """
        # 1. 创建适配器
        adapter = self._plugin_manager.create_instance(
            name=config.get("plugin", "local_oj"),
            base_url=config.get("base_url", "http://localhost:8080"),
        )
        if not adapter:
            raise ValueError(f"未知插件: {config.get('plugin')}")

        # 2. 生成用例
        cases = self._case_builder.build({
            "problem_id": config.get("problem_id", "1"),
            "strategies": config.get("strategies", ["random", "boundary", "rule"]),
            "count": config.get("case_count", 5),
        })

        # 3. 执行
        executor = SequentialExecutor(
            poll_interval=config.get("poll_interval", 1.0),
            poll_timeout=config.get("poll_timeout", 60),
        )

        return executor.execute(
            cases=cases,
            adapter=adapter,
            login_required=config.get("login_required", True),
            username=config.get("username", "admin"),
            password=config.get("password", ""),
        )
