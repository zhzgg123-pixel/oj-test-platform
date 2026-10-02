"""
FastAPI 应用入口

提供 REST API：
- /api/tasks/* — 任务管理
- /api/config — 配置管理
- /api/reports/* — 报告查询
- /api/plugins/* — 插件管理
"""

from __future__ import annotations
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config_center.config import AppConfig
from plugins.plugin_manager import PluginManager
from task_center.task_manager import TaskManager
from backend.routers import task_router, config_router, report_router, plugin_router

logger = logging.getLogger("oj.backend")


def create_app(config_path: str | None = None) -> FastAPI:
    """
    创建并配置 FastAPI 应用

    Args:
        config_path: 配置文件路径，为 None 则自动加载

    Returns:
        FastAPI 应用实例
    """
    # 加载配置
    app_config = AppConfig.load()
    logger.info("[Backend] 配置加载完成, env=%s", app_config.env)

    # 初始化插件管理器
    plugin_manager = PluginManager()
    plugins = plugin_manager.list_plugins()
    logger.info("[Backend] 已加载 %d 个插件: %s", len(plugins), [p["name"] for p in plugins])

    # 初始化任务管理器
    task_manager = TaskManager(
        report_dir=app_config.test.report_dir,
    )

    # 创建 FastAPI 实例
    app = FastAPI(
        title="OJ Test Platform API",
        description="自动化测试平台后端服务",
        version="1.0.0",
    )

    # CORS 配置（允许前端跨域访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注入全局状态
    app.state.app_config = app_config
    app.state.plugin_manager = plugin_manager
    app.state.task_manager = task_manager

    # 注册路由
    app.include_router(task_router.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(config_router.router, prefix="/api/config", tags=["config"])
    app.include_router(report_router.router, prefix="/api/reports", tags=["reports"])
    app.include_router(plugin_router.router, prefix="/api/plugins", tags=["plugins"])

    @app.get("/api/health")
    async def health():
        """健康检查"""
        return {"status": "ok", "plugins": len(plugin_manager.list_plugins())}

    @app.get("/")
    async def root():
        """根路径提示"""
        return {
            "message": "OJ Test Platform API",
            "docs": "/docs",
            "frontend": "/frontend/index.html",
        }

    return app


# 方便直接运行的实例
app = create_app()
