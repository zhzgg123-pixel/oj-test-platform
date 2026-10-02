"""
随机数据生成策略 - RandomGenerator

从代码模板池中随机选取 AC/CE/WA/TLE 代码，模拟真实用户提交。
"""

from .base_generator import BaseGenerator, TestCase


class RandomGenerator(BaseGenerator):
    """随机数据生成策略"""

    CODE_POOL = {
        "AC": (
            "#include <iostream>\n"
            "int main() {\n"
            "    int a, b;\n"
            "    std::cin >> a >> b;\n"
            "    std::cout << a + b << std::endl;\n"
            "    return 0;\n"
            "}"
        ),
        "CE": (
            "#include <iostream>\n"
            "int main() {\n"
            "    std::cout << 1 << std::endl\n"  # 缺少分号 => CE
            "    return 0\n"
            "}"
        ),
        "WA": (
            "#include <iostream>\n"
            "int main() {\n"
            "    int a, b;\n"
            "    std::cin >> a >> b;\n"
            "    std::cout << a - b << std::endl;\n"  # 减号 => WA
            "    return 0;\n"
            "}"
        ),
        "TLE": (
            "#include <iostream>\n"
            "int main() {\n"
            "    while (true) {}\n"  # 死循环 => TLE
            "    return 0;\n"
            "}"
        ),
    }

    def generate(self, spec: dict) -> list[TestCase]:
        import random

        count = spec.get("count", 5)
        problem_id = spec.get("problem_id", "1")
        statuses = spec.get("statuses", ["AC", "CE", "WA", "TLE"])
        rng = random.Random(spec.get("seed", 42))

        cases = []
        for i in range(count):
            status = rng.choice(statuses)
            code = self.CODE_POOL.get(status, self.CODE_POOL["AC"])
            cases.append(
                TestCase(
                    id=f"RANDOM-{problem_id}-{i+1:03d}",
                    desc=f"随机生成-{status}-第{i+1}条",
                    problem_id=problem_id,
                    code=code,
                    expected_status=status,
                    tags=["random", status.lower()],
                    priority="P2",
                    metadata={"generator": "random", "seed": 42},
                )
            )
        return cases
