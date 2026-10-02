"""
统一 API 响应模型

无论底层接口返回 JSON 还是 HTML，统一封装为 ApiResult。
上层（执行器、断言层）只与 ApiResult 交互。
"""

from dataclasses import dataclass
from typing import Any, Optional
import json


@dataclass
class ApiResult:
    """统一 API 响应模型"""

    success: bool
    status_code: int
    data: Any = None
    message: str = ""
    elapsed: float = 0.0
    raw: Optional[Any] = None

    @property
    def is_2xx(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_4xx(self) -> bool:
        return 400 <= self.status_code < 500

    @property
    def is_ok(self) -> bool:
        """业务成功（非 HTTP 层面的成功）"""
        return self.success

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "status_code": self.status_code,
            "data": self.data,
            "message": self.message,
            "elapsed": round(self.elapsed, 3),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
