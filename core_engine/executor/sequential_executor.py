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
        """执行单个测试用例"""
        cr = CaseResult(case=case, status="RUNNING", start_time=time.time())

        try:
            # 1. 提交代码
            submit_r = adapter.submit_code(case.problem_id, case.code, case.lang)
            if not submit_r.success:
                if case.expected_status == "ERROR":
                    cr.status = "PASSED"
                    cr.actual_status = "ERROR"
                else:
                    cr.status = "ERROR"
                    cr.error_message = f"提交失败: {submit_r.message}"
                cr.end_time = time.time()
                return cr

            # 2. 获取判题结果（优先从提交响应中直接获取，否则轮询）
            judge_r = submit_r.judge_result
            if judge_r is None:
                # 异步判题模式：需要提交后轮询
                judge_r = self._poll(adapter, submit_r.submit_id)

            if not judge_r:
                if case.expected_status == "ERROR":
                    cr.status = "PASSED"
                    cr.actual_status = "ERROR"
                    cr.end_time = time.time()
                    return cr
                cr.status = "ERROR"
                cr.error_message = f"判题超时（{self.poll_timeout}s）"
                cr.end_time = time.time()
                return cr

            # 3. 记录结果
            cr.judge_result = judge_r
            cr.actual_status = judge_r.status

            # 特殊语义：expected_status="ERROR" 表示预期失败
            if case.expected_status == "ERROR":
                cr.status = "PASSED"  # 触发了错误 → 期望的结果
            else:
                cr.status = "PASSED" if judge_r.status == case.expected_status else "FAILED"

        except Exception as e:
            if case.expected_status == "ERROR":
                cr.status = "PASSED"
                cr.actual_status = "ERROR"
            else:
                cr.status = "ERROR"
                cr.error_message = str(e)

        cr.end_time = time.time()
        return cr

    def _poll(self, adapter: BaseOJAdapter, submit_id: str) -> Optional[JudgeResult]:
        """轮询判题结果"""
        from plugins.base_adapter import JudgeResult

        deadline = time.time() + self.poll_timeout
        while time.time() < deadline:
            result = adapter.get_judge_result(submit_id)
            if result is not None:
                return result
            time.sleep(self.poll_interval)
        return None
