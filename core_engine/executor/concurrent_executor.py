"""
并发执行器 - ConcurrentExecutor

增强功能：使用 ThreadPoolExecutor 并发提交多个测试用例。

设计：
- 继承 BaseExecutor，复用 _execute_one 逻辑
- 通过 max_workers 控制并发度
- 每个用例独立提交和轮询，互不阻塞
"""

from __future__ import annotations
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from core_engine.case_engine.base_generator import TestCase
from core_engine.executor.base_executor import BaseExecutor, CaseResult, TaskResult
from core_engine.executor.sequential_executor import SequentialExecutor
from plugins.base_adapter import BaseOJAdapter

logger = logging.getLogger("oj.executor.concurrent")


class ConcurrentExecutor(BaseExecutor):
    """
    并发执行器

    使用 ThreadPoolExecutor 并发提交判题，显著减少批量执行的总耗时。

    使用方式：
        executor = ConcurrentExecutor(max_workers=5)
        result = executor.execute(cases, adapter, username="admin", password="EXAMPLE_PASSWORD")
    """

    def __init__(
        self,
        poll_interval: float = 1.0,
        poll_timeout: int = 60,
        max_workers: int = 5,
    ):
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.max_workers = max_workers
        # 复用 SequentialExecutor 的单用例执行逻辑
        self._seq = SequentialExecutor(
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    def execute(
        self,
        cases: list[TestCase],
        adapter: BaseOJAdapter,
        **kwargs,
    ) -> TaskResult:
        """
        并发执行全部测试用例

        Args:
            cases: 测试用例列表
            adapter: OJ 适配器
            **kwargs: username, password, login_required 等

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

        # 并发执行
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_case = {
                pool.submit(self._execute_one_safe, case, adapter): case
                for case in cases
            }

            for future in as_completed(future_to_case):
                case = future_to_case[future]
                try:
                    cr = future.result()
                except Exception as e:
                    cr = CaseResult(
                        case=case,
                        status="ERROR",
                        error_message=str(e),
                        start_time=result.start_time,
                        end_time=time.time(),
                    )

                result.case_results.append(cr)
                if cr.passed:
                    result.passed += 1
                elif cr.status == "ERROR":
                    result.error += 1
                else:
                    result.failed += 1

        result.end_time = time.time()
        logger.info(
            "[ConcurrentExecutor] %d 用例并发执行完成, 耗时 %.2fs (max_workers=%d)",
            len(cases), result.duration, self.max_workers,
        )
        return result

    def _execute_one_safe(self, case: TestCase, adapter: BaseOJAdapter) -> CaseResult:
        """安全执行单个用例（包装 SequentialExecutor 的内部逻辑）"""
        return self._seq._execute_one(case, adapter)
