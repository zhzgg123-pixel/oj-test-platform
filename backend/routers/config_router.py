"""
配置管理路由

API:
- GET  /api/config        — 获取当前配置
- POST /api/config/reload — 重新加载配置
"""

from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException

from config_center.config import AppConfig

router = APIRouter()


@router.get("")
async def get_config(request: Request):
    """获取当前配置"""
    app_config = request.app.state.app_config
    return {
        "success": True,
        "config": {
            "env": app_config.env,
            "oj": {
                "base_url": app_config.oj.base_url,
                "timeout": app_config.oj.timeout,
                "retry_count": app_config.oj.retry_count,
                "retry_delay": app_config.oj.retry_delay,
            },
            "judge": {
                "poll_interval": app_config.judge.poll_interval,
                "poll_timeout": app_config.judge.poll_timeout,
                "max_concurrent": app_config.judge.max_concurrent,
            },
            "test": {
                "log_level": app_config.test.log_level,
                "report_dir": app_config.test.report_dir,
                "case_strategies": app_config.test.case_strategies,
                "generate_case_count": app_config.test.generate_case_count,
            },
        },
    }


@router.post("/reload")
async def reload_config(request: Request):
    """重新加载配置"""
    try:
        refreshed = AppConfig.load(config_path=request.app.state.config_path)
    except (ValueError, OSError):
        raise HTTPException(422, detail="Invalid configuration; active configuration retained") from None
    # Existing task manager/report resources keep their startup destination until restart.
    if refreshed.test.report_dir != request.app.state.app_config.test.report_dir:
        raise HTTPException(409, detail="Changing report_dir requires application restart")
    request.app.state.app_config = refreshed
    return {"status": "ok", "message": "配置已重新加载"}
