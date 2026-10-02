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
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"    # 已取消

    def __str__(self) -> str:
        return self.value


from config_center.models import TaskConfig


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
