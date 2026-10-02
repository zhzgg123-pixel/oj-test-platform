"""
用例生成器 - 抽象基类

策略模式：所有生成器继承 BaseGenerator，实现 generate 方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TestCase:
    """统一测试用例模型"""

    id: str
    desc: str
    problem_id: str
    code: str
    lang: str = "cpp"
    expected_status: str = "AC"
    tags: list[str] = field(default_factory=list)
    priority: str = "P1"
    metadata: dict = field(default_factory=dict)


class BaseGenerator(ABC):
    """用例生成器抽象基类"""

    @abstractmethod
    def generate(self, spec: dict) -> list[TestCase]:
        """
        根据 spec 生成测试用例列表

        Args:
            spec: 生成规格
                - problem_id: 题目 ID
                - count: 生成数量
                - statuses: 可选的状态列表

        Returns:
            list[TestCase]: 生成的测试用例
        """
        ...
