"""
任务管理器 - TaskManager

文档规范：
- create_task(config) -> Task
- start_task(task_id) -> bool
- get_task(task_id) -> Task
- list_tasks(limit=20) -> list[Task]

使用内存存储（MVP 阶段），后续可替换为数据库/Redis。
"""

from __future__ import annotations
import uuid
import logging
import threading
from datetime import datetime
from typing import Optional

from task_center.models import Task, TaskConfig, TaskStatus
from core_engine.executor.task_executor import TaskExecutor
from core_engine.report_engine.report_generator import ReportGenerator

logger = logging.getLogger("oj.task_manager")


class TaskManager:
    """任务管理器 - 创建 / 调度 / 状态管理"""

    def __init__(self, report_dir: str = "reports"):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._executor = TaskExecutor()
        self._report_gen = ReportGenerator(output_dir=report_dir)

    def create_task(self, config: TaskConfig | dict) -> Task:
        """
        创建新任务

        Args:
            config: 任务配置（TaskConfig 对象或字典）

        Returns:
            Task: 创建的任务
        """
        if isinstance(config, dict):
            config = TaskConfig(**config)

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            name=f"测试任务-{task_id[-6:]}",
            config=config,
            status=TaskStatus.PENDING,
        )

        with self._lock:
            self._tasks[task_id] = task

        logger.info("[TaskManager] 任务已创建: %s", task_id)
        return task

    def start_task(self, task_id: str) -> bool:
        """
        异步启动任务

        Args:
            task_id: 任务 ID

        Returns:
            bool: 是否成功启动
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return False
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()  # type: ignore

        thread = threading.Thread(
            target=self._run,
            args=(task_id,),
            daemon=True,
        )
        thread.start()
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> list[Task]:
        """列出最近任务（按创建时间倒序）"""
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.created_at,
                reverse=True,
            )[:limit]
            return tasks

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status in (
                TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
            ):
                return False
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now().isoformat()
        return True

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if task_id not in self._tasks:
                return False
            del self._tasks[task_id]
        return True

    def _run(self, task_id: str) -> None:
        """后台执行任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

        try:
            # 执行测试（TaskExecutor 内部完成 用例生成 + 执行）
            task_result = self._executor.run_task(
                task_id=task_id,
                config=task.config.to_task_executor_config(),
            )

            # 生成报告
            report_info = self._report_gen.generate(
                task_result=task_result,
                task_config=task.config.to_dict(),
            )

            # 更新任务状态
            with self._lock:
                task = self._tasks.get(task_id)
                if not task:
                    return
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.progress_desc = "完成"
                task.result = {
                    "total": task_result.total,
                    "passed": task_result.passed,
                    "failed": task_result.failed,
                    "error": task_result.error,
                    "pass_rate": task_result.pass_rate,
                    "duration": task_result.duration,
                    "report_paths": {
                        "json": report_info["json_path"],
                        "html": report_info["html_path"],
                    },
                    "details": [
                        {
                            "case_id": cr.case.id,
                            "description": cr.case.desc,
                            "expected": cr.case.expected_status,
                            "actual": cr.actual_status,
                            "status": cr.status,
                            "passed": cr.passed,
                            "elapsed": cr.duration,
                        }
                        for cr in task_result.case_results
                    ],
                }
                task.updated_at = datetime.now().isoformat()

        except Exception as e:
            logger.exception("[TaskManager] 任务执行异常: %s", task_id)
            with self._lock:
                task = self._tasks.get(task_id)
                if not task:
                    return
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                task.updated_at = datetime.now().isoformat()
