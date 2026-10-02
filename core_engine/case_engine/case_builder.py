"""
用例构建器 - CaseBuilder

组合多策略生成测试用例，负责任务：
1. 根据配置选择生成策略
2. 调用对应生成器生成用例
3. 合并、排序（P0→P1→P2）
4. 输出最终用例列表
"""

from typing import Optional
from .base_generator import BaseGenerator, TestCase
from .random_generator import RandomGenerator
from .boundary_generator import BoundaryGenerator
from .rule_generator import RuleGenerator


class CaseBuilder:
    """用例构建器 - 组合多策略"""

    def __init__(self):
        self._generators: dict[str, BaseGenerator] = {
            "random": RandomGenerator(),
            "boundary": BoundaryGenerator(),
            "rule": RuleGenerator(),
        }

    def build(self, spec: dict) -> list[TestCase]:
        """
        构建测试用例集

        Args:
            spec: 构建规格
                - strategies: 使用的策略列表
                - problem_id: 题目 ID
                - count: 随机生成数量
                - filters: 规则筛选条件

        Returns:
            排序后的测试用例列表
        """
        strategies = spec.get("strategies", ["random", "boundary", "rule"])
        if not isinstance(strategies, list) or not strategies:
            raise ValueError("at least one strategy is required")
        count = spec.get("count", 5)
        if type(count) is not int or not 1 <= count <= 1000:
            raise ValueError("count must be an integer between 1 and 1000")
        for name in strategies:
            if name not in self._generators:
                raise ValueError(f"unknown strategy: {name}")
        all_cases: list[TestCase] = []
        for strategy_name in strategies:
            cases = self._generators[strategy_name].generate(spec)
            if not cases:
                raise ValueError(f"strategy generated no cases: {strategy_name}")
            all_cases.extend(cases)

        # P0 → P1 → P2
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        all_cases.sort(key=lambda c: priority_order.get(c.priority, 99))

        return all_cases

    def register_generator(self, name: str, generator: BaseGenerator) -> None:
        """注册自定义生成器（扩展点）"""
        self._generators[name] = generator
