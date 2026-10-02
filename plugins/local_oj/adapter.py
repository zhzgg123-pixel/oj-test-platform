"""
LocalOJAdapter - cpp-oj 系统的适配器实现

该 OJ 系统特点：
- 认证方式：Cookie + Session
- 判题为同步（提交后直接返回判题结果，无需轮询）
"""

from __future__ import annotations
from typing import Optional, Any
from ..base_adapter import BaseOJAdapter, LoginResult, SubmitResult, JudgeResult
from core_engine.api_client.request_client import RequestClient


class LocalOJAdapter(BaseOJAdapter):
    """cpp-oj 系统适配器"""

    def __init__(self, base_url: str, timeout: int = 30):
        super().__init__(base_url, timeout)
        self._client = RequestClient(
            base_url=base_url,
            timeout=timeout,
        )
        # 存储最近一次提交的判题结果（同步判题，无需轮询）
        self._last_judge_result: Optional[JudgeResult] = None

    def health_check(self) -> bool:
        """检查 cpp-oj 服务是否可用"""
        try:
            self._client.get("/")
            return True
        except Exception:
            return False

    def login(self, username: str, password: str) -> LoginResult:
        """
        POST /api/login
        Cookie 由 RequestClient 自动维护
        """
        try:
            resp = self._client.post(
                "/api/login",
                data={"username": username, "password": password},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return LoginResult(
                        success=True,
                        session_id=self._client.get_session_id(),
                    )
            return LoginResult(success=False, message=f"登录失败: HTTP {resp.status_code}")
        except Exception as e:
            return LoginResult(success=False, message=str(e))

    def submit_code(self, problem_id: str, code: str, lang: str = "cpp") -> SubmitResult:
        """
        POST /api/submit/{problem_id}

        该 OJ 同步判题，提交后直接返回判题结果。
        将结果缓存到 self._last_judge_result 供 get_judge_result() 读取。
        """
        self._last_judge_result = None

        try:
            resp = self._client.post(
                f"/api/submit/{problem_id}",
                data={"code": code, "lang": lang},
            )
            if resp.status_code == 200:
                data = resp.json()

                # 判题结果直接包含在响应中
                result_status = data.get("result", "")

                if result_status:
                    # 映射字段名（该 OJ 使用 result/compile_error/time_ms/memory_kb）
                    self._last_judge_result = JudgeResult(
                        status=result_status,
                        passed=data.get("passed", 0),
                        total=data.get("total", 0),
                        time_used_ms=data.get("time_ms", 0) or 0,
                        memory_used_kb=data.get("memory_kb", 0) or 0,
                        compile_msg=data.get("compile_error", "") or "",
                        run_msg=data.get("detail", "") or "",
                        raw_response=data,
                    )

                return SubmitResult(
                    success=True,
                    submit_id="",  # 同步判题，无 submit_id
                    message="提交成功（同步判题）",
                    judge_result=self._last_judge_result,
                )
            return SubmitResult(success=False, message=f"提交失败: HTTP {resp.status_code}")
        except Exception as e:
            return SubmitResult(success=False, message=str(e))

    def get_judge_result(self, submit_id: str) -> Optional[JudgeResult]:
        """
        获取判题结果。

        该 OJ 为同步判题，没有 /api/result/{id} 轮询接口。
        直接从 submit_code() 缓存的结果返回。
        """
        return self._last_judge_result

    def get_problem_list(self) -> list[dict]:
        """GET /api/problems 获取题目列表"""
        try:
            resp = self._client.get("/api/problems")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("problems", data if isinstance(data, list) else [])
            return []
        except Exception:
            return []

    def get_problem_detail(self, problem_id: str) -> Optional[dict]:
        """GET /api/problems/{id} 获取题目详情"""
        try:
            resp = self._client.get(f"/api/problems/{problem_id}")
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, dict) else data.get("problem")
            return None
        except Exception:
            return None
