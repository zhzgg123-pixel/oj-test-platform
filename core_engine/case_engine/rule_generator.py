"""
规则生成策略 - RuleGenerator

基于业务规则模板构造测试场景。
覆盖认证、权限、判题、参数校验等类别。

注意：预期状态需要针对目标 OJ 的实际行为调整。
当前适配的 OJ 特点：
- 不限制未登录提交
- 不限制普通用户访问管理 API
- 同步判题（提交即返回结果）
"""

from .base_generator import BaseGenerator, TestCase


class RuleGenerator(BaseGenerator):
    """规则模板生成策略"""

    RULES = [
        # ── 认证与权限（该 OJ 不限制未登录访问，用例验证提交行为而非权限）──
        {
            "id": "AUTH-UNATH-SUBMIT",
            "desc": "未登录提交代码（该 OJ 允许，验证提交接口正常）",
            "code": (
                "#include <iostream>\n"
                "int main() { int a,b; std::cin >> a >> b; std::cout << a + b; return 0; }"
            ),
            "expected": "AC",
            "tags": ["auth", "smoke"],
            "priority": "P1",
        },
        # ── 判题核心 ──
        {
            "id": "JUDGE-A+B-AC",
            "desc": "A+B问题的标准AC解法",
            "code": (
                "#include <iostream>\n"
                "int main() { int a,b; std::cin >> a >> b; std::cout << a + b; return 0; }"
            ),
            "expected": "AC",
            "tags": ["judge", "core"],
            "priority": "P0",
        },
        {
            "id": "JUDGE-A+B-WA",
            "desc": "A+B问题输出a-b（错误减法）",
            "code": (
                "#include <iostream>\n"
                "int main() { int a,b; std::cin >> a >> b; std::cout << a - b; return 0; }"
            ),
            "expected": "WA",
            "tags": ["judge", "core"],
            "priority": "P0",
        },
        {
            "id": "JUDGE-A+B-TLE",
            "desc": "A+B问题死循环（TLE）",
            "code": "#include <iostream>\nint main() { while (1) {} return 0; }",
            "expected": "TLE",
            "tags": ["judge", "core"],
            "priority": "P0",
        },
        {
            "id": "JUDGE-A+B-RE",
            "desc": "A+B问题空指针解引用（RE）",
            "code": (
                "#include <iostream>\n"
                "int main() { int* p = nullptr; *p = 42; return 0; }"
            ),
            "expected": "RE",
            "tags": ["judge", "core"],
            "priority": "P0",
        },
        # ── 参数校验 ──
        {
            "id": "PARAM-INVALID-LANG",
            "desc": "不支持的语言类型提交（Python代码→CE）",
            "code": "print(1+2)",
            "expected": "CE",
            "tags": ["param", "validation"],
            "priority": "P1",
        },
        {
            "id": "PARAM-SPECIAL-CHARS",
            "desc": "代码中包含中文注释",
            "code": (
                "#include <iostream>\n"
                "/* 你好世界 */\n"
                "int main() { int a,b; std::cin >> a >> b; std::cout << a + b; return 0; }"
            ),
            "expected": "AC",
            "tags": ["param", "encoding"],
            "priority": "P1",
        },
    ]

    def generate(self, spec: dict) -> list[TestCase]:
        problem_id = spec.get("problem_id", "1")
        filters = spec.get("filters", {})

        cases = []
        for rule in self.RULES:
            # 按标签筛选
            if "tags" in filters:
                if not any(t in rule.get("tags", []) for t in filters["tags"]):
                    continue
            # 按优先级筛选
            if "priority" in filters:
                if rule.get("priority", "P2") != filters["priority"]:
                    continue

            cases.append(
                TestCase(
                    id=rule["id"],
                    desc=rule["desc"],
                    problem_id=problem_id,
                    code=rule["code"],
                    expected_status=rule["expected"],
                    tags=rule.get("tags", []),
                    priority=rule.get("priority", "P2"),
                    metadata={"generator": "rule", "rule_id": rule["id"]},
                )
            )

        return cases
