"""
用例生成器 - 抽象基类

策略模式：所有生成器继承 BaseGenerator，实现 generate 方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
from core_engine.contracts import Expectation


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
    expectation: Expectation | None = None
    strategy: str = 'manual'
    profile_id: str = ''
    profile_sha256: str = ''
    source_sha256: str = ''
    seed: int | None = None
    auth_mode: str = 'authenticated'
    request_overrides: dict = field(default_factory=dict)

    def __post_init__(self):
        self.source_sha256 = hashlib.sha256(self.code.encode('utf-8')).hexdigest()

    @property
    def source_code(self):
        return self.code


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
