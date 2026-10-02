"""
结果校验器 - JudgeOracle

Oracle 规则引擎 - 判题结果自动校验

设计思路：将判题规则集中管理，新增状态只需在 RULES 中添加一条规则。

文档规范要求：
- RULES 字典 + lambda checker（AC/WA/CE/TLE/RE/MLE）
- verify() 方法接收 judge_result + expected_status
- 返回 OracleResult
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class OracleResult:
    """Oracle 规则判定结果"""

    passed: bool
    expected: str
    actual: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


class JudgeOracle:
    """
    Oracle 规则引擎 - 判题结果自动校验

    设计思路：将判题规则集中管理，新增状态只需在 RULES 中添加一条规则。

    使用方式：
        oracle = JudgeOracle()
        result = oracle.verify(judge_result, "AC")
        # result.passed == True/False
    """

    RULES: dict[str, dict] = {
        "AC":  {"check": lambda r: r.get("passed", 0) > 0 and r.get("passed") == r.get("total"),
                "desc": "全部测试用例通过"},
        "WA":  {"check": lambda r: r.get("passed", 0) < r.get("total", 1),
                "desc": "输出结果与预期不符"},
        "CE":  {"check": lambda r: bool(r.get("compile_msg", "")),
                "desc": "编译错误"},
        "TLE": {"check": lambda r: r.get("time_used_ms", 0) >= 1000,
                "desc": "运行超时"},
        "RE":  {"check": lambda r: r.get("exit_code", 0) != 0,
                "desc": "运行时错误"},
        "MLE": {"check": lambda r: r.get("memory_used_kb", 0) >= 65536,
                "desc": "内存超限"},
    }

    def verify(self, judge_result: Any, expected_status: str) -> OracleResult:
        """
        校验判题结果是否符合预期

        Args:
            judge_result: 判题结果对象（JudgeResult 或 dict）
            expected_status: 预期状态（如 AC / WA / CE）

        Returns:
            OracleResult: 规则判定结果
        """
        # 统一转为 dict
        result_dict = (
            judge_result.__dict__
            if hasattr(judge_result, "__dict__")
            else (judge_result if isinstance(judge_result, dict) else {})
        )

        rule = self.RULES.get(expected_status.upper())
        if not rule:
            # 无对应规则时，做简单的字符串比对
            actual = result_dict.get("status", "")
            return OracleResult(
                passed=(actual == expected_status),
                expected=expected_status,
                actual=actual,
                detail="无对应规则，使用精确匹配",
            )

        try:
            passed = rule["check"](result_dict)
            actual = result_dict.get("status", "UNKNOWN")
            return OracleResult(
                passed=passed,
                expected=expected_status,
                actual=actual,
                detail=rule["desc"],
            )
        except Exception as e:
            return OracleResult(
                passed=False,
                expected=expected_status,
                actual=str(result_dict),
                detail=f"规则校验异常: {e}",
            )

    @classmethod
    def register_rule(cls, status: str, check_func: Callable, desc: str = "") -> None:
        """注册自定义校验规则（扩展点）"""
        cls.RULES[status.upper()] = {"check": check_func, "desc": desc}

    @classmethod
    def get_supported_statuses(cls) -> list[str]:
        """获取所有支持的判题状态"""
        return list(cls.RULES.keys())
