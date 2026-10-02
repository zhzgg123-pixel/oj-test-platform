"""
统一 HTTP 客户端封装 - RequestClient

核心能力：
1. requests.Session 自动管理 Cookie
2. 统一超时控制
3. 自动重试（5xx / 超时）
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
        """
        统一请求入口，含重试与日志

        Args:
            method: HTTP 方法
            path: API 路径（如 /api/login）
            **kwargs: 传给 requests 的参数

        Returns:
            requests.Response

        Raises:
            ConnectionError: 所有重试耗尽后仍连接失败
            RuntimeError: 所有重试耗尽后仍返回 5xx
        """
        url = urljoin(self.base_url, path)
        kwargs.setdefault("timeout", self.timeout)
        last_exception = None

        for attempt in range(1, self.retry_count + 1):
            try:
                start = time.time()
                response = self._session.request(method, url, **kwargs)
                elapsed = time.time() - start

                logger.debug(
                    "[HTTP] %s %s → %d (%.3fs) [%d/%d]",
                    method, url, response.status_code, elapsed,
                    attempt, self.retry_count,
                )

                # 非 5xx 错误直接返回
                if response.status_code < 500:
                    return response

                # 5xx 重试
                logger.warning(
                    "[HTTP] %s %s → %d, 重试中... [%d/%d]",
                    method, url, response.status_code, attempt, self.retry_count,
                )

            except requests.Timeout as e:
                last_exception = e
                logger.warning(
                    "[HTTP] %s %s 超时 (%.1fs), 重试中... [%d/%d]",
                    method, url, self.timeout, attempt, self.retry_count,
                )
            except requests.ConnectionError as e:
                last_exception = e
                logger.error(
                    "[HTTP] %s %s 连接失败: %s [%d/%d]",
                    method, url, str(e), attempt, self.retry_count,
                )
                if attempt == self.retry_count:
                    raise

            # 退避等待
            if attempt < self.retry_count:
                time.sleep(self.retry_delay * attempt)

        # 所有重试耗尽
        if last_exception:
            raise last_exception  # type: ignore

        # 所有重试后仍是 5xx
        raise RuntimeError(f"[HTTP] 请求失败（重试耗尽）: {method} {url}")

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
