"""
执行器 - 抽象基类

文档规范要求：
- BaseExecutor 定义 execute() 抽象方法
- CaseResult 包含 start_time / end_time / duration / judge_result
- TaskResult 替代 ExecuteReport
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from core_engine.case_engine.base_generator import TestCase
from plugins.base_adapter import BaseOJAdapter, JudgeResult
from core_engine.contracts import Observation


@dataclass
class CaseResult:
    """单条用例执行结果"""

    case: TestCase
    status: str = "PENDING"       # PENDING / RUNNING / PASSED / FAILED / ERROR
    actual_status: str = ""
    judge_result: Optional[JudgeResult] = None
    error_message: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    observation: Observation | None = None
    attempt_count: int = 1

    @property
    def duration(self) -> float:
        """执行耗时（秒）"""
        if self.end_time and self.start_time:
            return round(self.end_time - self.start_time, 3)
        return 0.0

    @property
    def passed(self) -> bool:
        """是否通过"""
        return self.status == "PASSED"

    @property
    def summary(self) -> str:
        if self.status == "PASSED":
            return f"✅ {self.case.id} — {self.case.desc} (期望={self.case.expected_status}, 实际={self.actual_status})"
        elif self.status == "FAILED":
            return f"❌ {self.case.id} — {self.case.desc} (期望={self.case.expected_status}, 实际={self.actual_status})"
        elif self.status == "ERROR":
            return f"💥 {self.case.id} — {self.case.desc} ({self.error_message})"
        return f"⏳ {self.case.id} — {self.case.desc} ({self.status})"


@dataclass
class TaskResult:
    """一组用例执行结果汇总"""

    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
    case_results: list[CaseResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def pass_rate(self) -> float:
        return round(self.passed / self.total * 100, 2) if self.total else 0.0

    @property
    def duration(self) -> float:
        return round(self.end_time - self.start_time, 3) if self.end_time and self.start_time else 0.0

    @property
    def summary_line(self) -> str:
        return (
            f"总计 {self.total} 条 | "
            f"✅ 通过 {self.passed} | "
            f"❌ 失败 {self.failed} | "
            f"💥 错误 {self.error} | "
            f"通过率 {self.pass_rate}% | "
            f"耗时 {self.duration:.2f}s"
        )


class BaseExecutor(ABC):
    """执行器抽象基类"""

    @abstractmethod
    def execute(
        self,
        cases: list[TestCase],
        adapter: BaseOJAdapter,
        **kwargs,
    ) -> TaskResult:
        """
        执行全部测试用例

        Args:
            cases: 测试用例列表
            adapter: OJ 系统适配器
            **kwargs: 额外参数（如 username, password, poll_interval, poll_timeout）

        Returns:
            TaskResult: 执行结果
        """
        ...
