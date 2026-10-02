"""
SchoolOJAdapter - 学校 OJ 系统适配器示例

演示插件扩展能力：新增 OJ 只需写一个 adapter.py，不改框架代码。

该适配器模拟学校 OJ 的特点：
- 使用 Token 认证（而非 Cookie）
- 判题为同步接口（提交后直接返回结果，无需轮询）
- API 路径不同
"""

from __future__ import annotations
from typing import Optional, Any
from ..base_adapter import (
    BaseOJAdapter,
    LoginResult,
    SubmitResult,
    JudgeResult,
)
from core_engine.api_client.request_client import RequestClient


class SchoolOJAdapter(BaseOJAdapter):
    """
    学校 OJ 系统适配器（示例）

    演示了如何为不同 OJ 系统实现适配器：
    - 不同的认证方式（Token）
    - 不同的 API 路径
    - 同步判题（无需轮询）
    """

    def __init__(self, base_url: str, timeout: int = 30):
        super().__init__(base_url, timeout)
        self._client = RequestClient(base_url, timeout=timeout)
        self._token: Optional[str] = None

    def login(self, username: str, password: str) -> LoginResult:
        """
        学校 OJ 登录：POST /api/v2/login → 返回 Token

        将 Token 注入后续请求的 Authorization 头。
        """
        try:
            resp = self._client.post(
                "/api/v2/login",
                json={"username": username, "password": password},
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token") or data.get("access_token", "")
                if token:
                    self._token = token
                    self._client.set_header("Authorization", f"Bearer {token}")
                    return LoginResult(success=True, session_id=token)

            return LoginResult(
                success=False,
                message=f"登录失败: HTTP {resp.status_code}",
            )
        except Exception as e:
            return LoginResult(success=False, message=str(e))

    def submit_code(
        self,
        problem_id: str,
        code: str,
        lang: str = "cpp",
    ) -> SubmitResult:
        """
        学校 OJ 提交：POST /api/v2/submit

        同步判题模式：提交后立即返回判题结果，无需轮询。
        """
        try:
            resp = self._client.post(
                "/api/v2/submit",
                json={
                    "problem_id": problem_id,
                    "source_code": code,
                    "language": lang,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return SubmitResult(
                    success=True,
                    submit_id=str(data.get("submission_id", "")),
                    message="提交成功（同步判题）",
                )
            return SubmitResult(
                success=False,
                message=f"提交失败: HTTP {resp.status_code}",
            )
        except Exception as e:
            return SubmitResult(success=False, message=str(e))

    def get_judge_result(self, submit_id: str) -> Optional[JudgeResult]:
        """
        学校 OJ 查询判题结果：GET /api/v2/submissions/{id}

        由于是同步判题，通常提交时已有结果。此方法作为补充查询。
        """
        try:
            resp = self._client.get(f"/api/v2/submissions/{submit_id}")
            if resp.status_code != 200:
                return None

            data = resp.json()
            status_map = {
                "accepted": "AC",
                "wrong_answer": "WA",
                "compile_error": "CE",
                "time_limit_exceeded": "TLE",
                "memory_limit_exceeded": "MLE",
                "runtime_error": "RE",
            }
            raw_status = data.get("verdict", "").lower()
            mapped_status = status_map.get(raw_status, "UNKNOWN")

            return JudgeResult(
                status=mapped_status,
                passed=data.get("passed_cases", 0),
                total=data.get("total_cases", 0),
                time_used_ms=data.get("time_used_ms", 0),
                memory_used_kb=data.get("memory_kb", 0),
                compile_msg=data.get("compile_msg", ""),
                run_msg=data.get("error_info", ""),
                raw_response=data,
            )
        except Exception:
            return None

    def get_problem_list(self) -> list[dict]:
        """GET /api/v2/problems 获取题目列表"""
        try:
            resp = self._client.get("/api/v2/problems")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", data if isinstance(data, list) else [])
            return []
        except Exception:
            return []

    def get_problem_detail(self, problem_id: str) -> Optional[dict]:
        """GET /api/v2/problems/{id} 获取题目详情"""
        try:
            resp = self._client.get(f"/api/v2/problems/{problem_id}")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", data if isinstance(data, dict) else None)
            return None
        except Exception:
            return None
