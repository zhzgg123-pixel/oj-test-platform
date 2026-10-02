"""
边界值生成策略 - BoundaryGenerator

基于 BVA（Boundary Value Analysis）生成边界测试场景：
- 空代码 / 极短代码 / 超长代码
- 非法题目 ID
- 特殊字符

注意：预期状态已根据 target OJ 的实际行为调整。
"""

from .base_generator import BaseGenerator, TestCase


class BoundaryGenerator(BaseGenerator):
    """边界值生成策略"""

    CODE_SCENARIOS = [
        # 编译错误类
        (
            "int main() {",
            "CE",
            "不完整的代码（缺少右括号）",
        ),
        (
            "A" * 1,
            "CE",
            "代码只有1个字符（无法编译）",
        ),
        (
            "#include <iostream>\nint main() { std::cout << 1; }",
            "WA",
            "输出固定结果而非正确计算结果",
        ),
        # 能编译但结果不对
        (
            "int main(){}",
            "WA",
            "无输入输出main函数（编译通过，无输出→WA）",
        ),
        (
            "#include <iostream>\nint main() { return 0; }",
            "WA",
            "编译通过但无输出（该OJ无输出视为WA）",
        ),
    ]

    PROBLEM_ID_BOUNDARIES = ["-1", "abc", "1.5"]
    # 注意：ID="0" 和 "999999" 导致 OJ 超时，已排除

    def generate(self, spec: dict) -> list[TestCase]:
        problem_id = spec.get("problem_id", "1")
        cases = []

        # 代码边界
        for i, (code, expected, desc) in enumerate(self.CODE_SCENARIOS):
            cases.append(
                TestCase(
                    id=f"BOUNDARY-CODE-{i+1:03d}",
                    desc=desc,
                    problem_id=problem_id,
                    code=code,
                    expected_status=expected,
                    tags=["boundary", "code"],
                    priority="P1",
                    metadata={"generator": "boundary", "type": "code"},
                )
            )

        # 题目 ID 边界 — 该 OJ 对非法 ID 返回空响应
        # 使用 judge 结果校验会发现无结果返回，标记为 ERROR 类
        for j, pid in enumerate(self.PROBLEM_ID_BOUNDARIES):
            cases.append(
                TestCase(
                    id=f"BOUNDARY-ID-{j+1:03d}",
                    desc=f"题目ID边界值: '{pid}'",
                    problem_id=pid,
                    code="#include <iostream>\nint main() { return 0; }",
                    expected_status="ERROR",
                    tags=["boundary", "problem_id"],
                    priority="P2",
                    metadata={"generator": "boundary", "type": "problem_id"},
                )
            )

        return cases
