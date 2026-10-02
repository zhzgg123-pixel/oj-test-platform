"""
顺序执行器 - SequentialExecutor

逐个执行测试用例，每个用例经历：
1. 提交代码 → 2. 轮询判题结果 → 3. 记录结果

文档规范要求：
- execute() 接收 adapter: BaseOJAdapter 作为直接参数
- 登录逻辑在 execute 内部处理
- 状态用 PASSED / FAILED
"""

from __future__ import annotations
import time
import logging
from typing import Optional
from core_engine.case_engine.base_generator import TestCase
from core_engine.executor.base_executor import BaseExecutor, CaseResult, TaskResult
from plugins.base_adapter import BaseOJAdapter
from core_engine.contracts import Expectation, Observation
from core_engine.assertion.judge_oracle import JudgeOracle

logger = logging.getLogger("oj.executor")


class SequentialExecutor(BaseExecutor):
    """顺序执行器"""

    def __init__(self, poll_interval: float = 1.0, poll_timeout: int = 60):
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def execute(
        self,
        cases: list[TestCase],
        adapter: BaseOJAdapter,
        **kwargs,
    ) -> TaskResult:
        """
        顺序执行全部测试用例

        Args:
            cases: 测试用例列表
            adapter: OJ 系统适配器
            **kwargs: 支持 username, password, login_required

        Returns:
            TaskResult
        """
        result = TaskResult(total=len(cases), start_time=time.time())

        # 登录（如果需要）
        login_required = kwargs.get("login_required", True)
        if login_required:
            username = kwargs.get("username", "admin")
            password = kwargs.get("password", "")
            login_r = adapter.login(username, password)
            if not login_r.success:
                result.end_time = time.time()
                for case in cases:
                    cr = CaseResult(
                        case=case,
                        status="ERROR",
                        error_message=f"登录失败: {login_r.message}",
                        start_time=result.start_time,
                        end_time=time.time(),
                    )
                    result.case_results.append(cr)
                    result.error += 1
                return result

        # 逐个执行
        for case in cases:
            cr = self._execute_one(case, adapter)
            result.case_results.append(cr)
            if cr.passed:
                result.passed += 1
            elif cr.status == "ERROR":
                result.error += 1
            else:
                result.failed += 1

        result.end_time = time.time()
        return result

    def _execute_one(self, case: TestCase, adapter: BaseOJAdapter) -> CaseResult:
        """Validate intent first, then interpret only an explicit observation."""
        cr = CaseResult(case=case, status="RUNNING", start_time=time.time())
        try:
            try:
                expected = case.expectation or Expectation(kind="verdict", verdict=case.expected_status)
            except ValueError:
                cr.status = "ERROR"
                cr.error_message = "Invalid expectation: replace generic ERROR with a specific HTTP or business expectation"
                return cr

            submitted = adapter.submit_code(case.problem_id, case.code, case.lang)
            observed = submitted.observation
            judge = submitted.judge_result
            if observed is None:
                if not submitted.success:
                    observed = Observation(kind="protocol_error", error_code="UNSTRUCTURED_SUBMISSION_FAILURE")
                else:
                    if judge is None and submitted.submit_id:
                        judge = self._poll(adapter, submitted.submit_id)
                    if judge is None:
                        observed = Observation(kind="protocol_error", error_code=(
                            "POLL_TIMEOUT" if submitted.submit_id else "MISSING_VERDICT"))
                    else:
                        try:
                            observed = Observation(kind="verdict", verdict=judge.status, evidence=vars(judge))
                        except ValueError:
                            observed = Observation(kind="protocol_error", error_code="UNKNOWN_VERDICT")
            cr.judge_result = judge
            cr.observation = observed
            cr.actual_status = observed.verdict or observed.error_code or f"HTTP_{observed.http_status}"
            assertion = JudgeOracle().evaluate(expected, observed)
            cr.status = assertion.status
            if assertion.status != "PASSED":
                cr.error_message = assertion.reason
        except Exception as exc:
            # A platform exception is never proof that the expected OJ rejection occurred.
            cr.status = "ERROR"
            cr.error_message = f"Execution failed: {type(exc).__name__}"
            cr.observation = Observation(kind="protocol_error", error_code="EXECUTION_ERROR")
        finally:
            cr.end_time = time.time()
        return cr

    def _poll(self, adapter: BaseOJAdapter, submit_id: str) -> Optional[JudgeResult]:
        """轮询判题结果"""
        from plugins.base_adapter import JudgeResult

        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            result = adapter.get_judge_result(submit_id)
            if result is not None:
                return result
            time.sleep(self.poll_interval)
        return None
