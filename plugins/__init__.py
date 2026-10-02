"""插件系统模块"""

from plugins.base_adapter import BaseOJAdapter, JudgeResult, SubmitResult, LoginResult
from plugins.plugin_manager import PluginManager

__all__ = [
    "BaseOJAdapter",
    "JudgeResult",
    "SubmitResult",
    "LoginResult",
    "PluginManager",
]
