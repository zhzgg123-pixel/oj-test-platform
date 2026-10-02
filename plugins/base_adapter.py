"""
OJ 系统适配器抽象基类 - BaseOJAdapter

适配器模式：所有 OJ 系统通过继承此类实现适配，框架通过 PluginManager 动态加载。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core_engine.contracts import Observation


@dataclass
class JudgeResult:
    """统一的判题结果模型"""

    status: str  # AC / WA / CE / TLE / RE / MLE
    passed: int = 0
    total: int = 0
    time_used_ms: int = 0
    memory_used_kb: int = 0
    compile_msg: str = ""
    run_msg: str = ""
    raw_response: Optional[dict] = None

    @property
    def is_ac(self) -> bool:
        return self.status == "AC"

    @property
    def is_error(self) -> bool:
        return self.status in ("CE", "RE", "TLE", "MLE")


@dataclass
class SubmitResult:
    """提交结果"""
    success: bool
    submit_id: Optional[str] = None
    message: str = ""
    judge_result: Optional[JudgeResult] = None
    observation: Optional['Observation'] = None


@dataclass
class AuthResult:
    """登录结果"""
    success: bool
    session_id: Optional[str] = field(default=None, repr=False)
    message: str = ""


# Preserve the public name used by existing adapters while exposing the new contract.
LoginResult = AuthResult


class BaseOJAdapter(ABC):
    """
    OJ 系统适配器抽象基类。

    所有 OJ 系统（cpp-oj、LeetCode、POJ 等）通过继承此类实现适配。
    框架通过 PluginManager 动态加载和调用。
    """

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def submit_case(self, case):
        """New receipt interface; existing third-party submit_code plugins still work."""
        import uuid
        from core_engine.contracts import Observation, SubmissionReceipt
        result = self.submit_code(case.problem_id, case.code, case.lang)
        observed = result.observation
        if observed is None and result.judge_result is not None:
            observed = Observation(kind='verdict', verdict=result.judge_result.status,
                                   evidence=vars(result.judge_result))
        if observed is None and (not result.success or not result.submit_id):
            observed = Observation(kind='protocol_error', error_code='UNSTRUCTURED_SUBMISSION_FAILURE')
        return SubmissionReceipt(result.submit_id or 'local-' + uuid.uuid4().hex, observed)

    def get_result(self, submission_id):
        from core_engine.contracts import Observation
        result = self.get_judge_result(submission_id)
        if result is None:
            return None
        return Observation(kind='verdict', verdict=result.status, evidence=vars(result))

    def close(self):
        """Adapters that own a client override this to release connections."""

    @abstractmethod
    def login(self, username: str, password: str) -> LoginResult:
        """登录 OJ 系统"""

    @abstractmethod
    def submit_code(self, problem_id: str, code: str, lang: str = "cpp") -> SubmitResult:
        """提交代码"""

    @abstractmethod
    def get_judge_result(self, submit_id: str) -> Optional[JudgeResult]:
        """查询判题结果，返回 None 表示仍在判题中"""

    @abstractmethod
    def get_problem_list(self) -> list[dict]:
        """
        获取题目列表

        Returns:
            list[dict]: 每项含 id, title, difficulty 等字段
        """
        ...

    @abstractmethod
    def get_problem_detail(self, problem_id: str) -> Optional[dict]:
        """
        获取题目详情

        Args:
            problem_id: 题目 ID

        Returns:
            dict: 含 title, description, input_desc, output_desc,
                  sample_input, sample_output, time_limit, memory_limit 等
        """
        ...

    def health_check(self) -> bool:
        """检查 OJ 服务是否可用（子类可覆盖实现更精确的检测）

        默认实现：向 OJ 发送 GET 请求，能收到 HTTP 响应即视为可用。
        """
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(f"{self.base_url}/", method="GET")
            urllib.request.urlopen(req, timeout=self.timeout)
            return True
        except urllib.error.HTTPError:
            # 即使返回 4xx/5xx 也说明服务器在运行
            return True
        except Exception:
            return False
