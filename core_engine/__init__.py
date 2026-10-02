"""Core Engine — 测试核心引擎"""

from core_engine.case_engine import (
    BaseGenerator, TestCase, RandomGenerator,
    BoundaryGenerator, RuleGenerator, CaseBuilder,
)
from core_engine.api_client import RequestClient, ApiResult
from core_engine.assertion import JudgeOracle, OracleResult
from core_engine.executor import BaseExecutor, CaseResult, TaskResult, SequentialExecutor, ConcurrentExecutor, TaskExecutor
from core_engine.report_engine import ReportGenerator

__all__ = [
    # case_engine
    "BaseGenerator", "TestCase", "RandomGenerator",
    "BoundaryGenerator", "RuleGenerator", "CaseBuilder",
    # api_client
    "RequestClient", "ApiResult",
    # assertion
    "JudgeOracle", "OracleResult",
    # executor
    "BaseExecutor", "CaseResult", "TaskResult", "SequentialExecutor", "ConcurrentExecutor", "TaskExecutor",
    # report_engine
    "ReportGenerator",
]
