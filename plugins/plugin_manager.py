"""
插件管理器 - PluginManager

职责：
1. 扫描 plugins 目录加载所有适配器
2. 按名称查找适配器
3. 管理适配器实例（带缓存）
"""

from __future__ import annotations
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Optional
from .base_adapter import BaseOJAdapter


class PluginManager:
    """插件管理器"""

    def __init__(self):
        self._adapters: dict[str, type[BaseOJAdapter]] = {}
        self._instances: dict[str, BaseOJAdapter] = {}
        self._scan_plugins()

    def _scan_plugins(self) -> None:
        """扫描 plugins 目录，注册 BaseOJAdapter 子类"""
        plugins_dir = Path(__file__).parent

        for importer, modname, is_pkg in pkgutil.iter_modules([str(plugins_dir)]):
            if modname in ("base_adapter", "plugin_manager"):
                continue
            try:
                module = importlib.import_module(f"plugins.{modname}")
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseOJAdapter)
                        and obj is not BaseOJAdapter
                    ):
                        self._adapters[modname] = obj
            except Exception as e:
                print(f"[PluginManager] 加载插件 {modname} 失败: {e}")

        # 手动注册内置 LocalOJ 适配器
        from plugins.local_oj.adapter import LocalOJAdapter
        self._adapters["local_oj"] = LocalOJAdapter

    def list_plugins(self) -> list[dict]:
        """列出所有可用插件"""
        return [
            {"name": name, "class": adapter.__name__}
            for name, adapter in self._adapters.items()
        ]

    def get_adapter(self, name: str) -> Optional[type[BaseOJAdapter]]:
        """按名称获取适配器类"""
        return self._adapters.get(name)

    def create_instance(
        self, name: str, base_url: str, timeout: int = 30
    ) -> Optional[BaseOJAdapter]:
        """创建适配器实例（带缓存，相同 name+base_url 复用）"""
        cache_key = f"{name}@{base_url}"
        if cache_key in self._instances:
            return self._instances[cache_key]

        adapter_cls = self.get_adapter(name)
        if not adapter_cls:
            return None

        instance = adapter_cls(base_url=base_url, timeout=timeout)
        self._instances[cache_key] = instance
        return instance

    def remove_instance(self, name: str, base_url: str) -> None:
        """移除适配器实例"""
        cache_key = f"{name}@{base_url}"
        self._instances.pop(cache_key, None)
