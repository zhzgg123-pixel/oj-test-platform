"""
统一 HTTP 客户端封装 - RequestClient

核心能力：
1. requests.Session 自动管理 Cookie
2. 统一超时控制
3. 仅 GET 对指定瞬时错误有限重试；POST 不自动重发
4. 全链路请求/响应日志
5. 统一的异常处理
"""

from __future__ import annotations
import time
import logging
import requests
from typing import Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger("oj.api_client")


class RequestClient:
    """统一 HTTP 客户端封装"""

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self._session = requests.Session()

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, data: Any = None, json: Any = None, **kwargs) -> requests.Response:
        return self.request("POST", path, data=data, json=json, **kwargs)

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Retry only safe GET requests; preserve the final HTTP response for the adapter.

        retry_count is the total GET attempt count, bounded to three. A POST may
        already have been accepted when its response is lost, so it is sent once.
        """
        method = method.upper()
        url = urljoin(self.base_url, path)
        kwargs.setdefault("timeout", self.timeout)
        if method != "GET":
            # A 307/308 redirect can replay a POST too; return it for explicit handling.
            kwargs["allow_redirects"] = False
        attempts = min(3, max(1, self.retry_count)) if method == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.request(method, url, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == attempts:
                    raise
                logger.warning("GET transport failure; retry %d/%d", attempt, attempts)
            else:
                if response.status_code not in {502, 503, 504} or attempt == attempts:
                    return response
                response.close()
                logger.warning("GET transient HTTP failure; retry %d/%d", attempt, attempts)
            time.sleep(self.retry_delay * attempt)
        raise AssertionError("unreachable request retry state")

    def close(self) -> None:
        """Release this client's connection pool."""
        self._session.close()

    def get_session_id(self) -> Optional[str]:
        """获取当前 Session ID"""
        for cookie in self._session.cookies:
            if cookie.name.lower() in ("session_id", "sessionid", "sid", "token"):
                return cookie.value
        return None

    def clear_session(self) -> None:
        """清除当前 Session"""
        self._session.cookies.clear()

    def set_header(self, key: str, value: str) -> None:
        self._session.headers[key] = value

    @property
    def cookies(self) -> dict:
        return dict(self._session.cookies)
