"""
任务模型定义

包含：
- TaskStatus: 任务状态枚举
- TaskConfig: 任务配置
- Task: 任务对象

注意：TaskResult 由 executor.base_executor 定义，不在此处重复。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "PENDING"        # 等待执行
    RUNNING = "RUNNING"        # 执行中
    COMPLETED = "COMPLETED"    # 已完成
    FAILED = "FAILED"          # 失败
    CANCELLED = "CANCELLED"    # 已取消

    def __str__(self) -> str:
        return self.value


@dataclass
class TaskConfig:
    """任务配置"""

    # OJ 连接
    adapter_name: str = "local_oj"
    base_url: str = "http://localhost:8080"
    username: str = ""
    password: str = ""

    # 用例生成
    strategies: list[str] = field(default_factory=lambda: ["random", "boundary", "rule"])
    problem_id: str = "1"
    case_count: int = 5

    # 执行
    poll_interval: float = 1.0
    poll_timeout: int = 60
    timeout: int = 30

    def to_dict(self) -> dict:
        return {
            "adapter_name": self.adapter_name,
            "base_url": self.base_url,
            "username": self.username,
            "strategies": self.strategies,
            "problem_id": self.problem_id,
            "case_count": self.case_count,
            "poll_interval": self.poll_interval,
            "poll_timeout": self.poll_timeout,
            "timeout": self.timeout,
        }

    def to_task_executor_config(self) -> dict:
        """转为 TaskExecutor.run_task() 所需的 config 字典"""
        return {
            "plugin": self.adapter_name,
            "base_url": self.base_url,
            "username": self.username,
            "password": self.password,
            "problem_id": self.problem_id,
            "strategies": self.strategies,
            "case_count": self.case_count,
            "poll_interval": self.poll_interval,
            "poll_timeout": self.poll_timeout,
            "timeout": self.timeout,
        }


@dataclass
class Task:
    """任务对象"""

    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    config: TaskConfig = field(default_factory=TaskConfig)
    result: Optional[dict] = None   # TaskResult.to_dict() 的序列化结果
    progress: int = 0               # 0-100
    progress_desc: str = ""
    created_at: str = ""
    updated_at: str = ""
    error_message: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress,
            "progress_desc": self.progress_desc,
            "config": self.config.to_dict(),
            "result": self.result,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
