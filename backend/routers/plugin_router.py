"""
插件管理路由

API:
- GET  /api/plugins       — 插件列表
- POST /api/plugins/test  — 测试插件连接
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class TestPluginRequest(BaseModel):
    """测试插件连接请求"""
    adapter_name: str = "local_oj"
    base_url: str = "http://localhost:8080"
    username: str = ""
    password: str = ""
    timeout: int = 10


@router.get("")
async def list_plugins(request: Request):
    """列出所有可用插件"""
    plugin_manager = request.app.state.plugin_manager
    plugins = plugin_manager.list_plugins()
    return {"success": True, "plugins": plugins, "total": len(plugins)}


@router.post("/test")
async def test_plugin(req: TestPluginRequest, request: Request):
    """测试 OJ 连接"""
    plugin_manager = request.app.state.plugin_manager
    adapter = plugin_manager.create_instance(
        name=req.adapter_name,
        base_url=req.base_url,
        timeout=req.timeout,
    )

    if not adapter:
        raise HTTPException(status_code=400, detail=f"未知适配器: {req.adapter_name}")

    try:
        if req.username and req.password:
            result = adapter.login(req.username, req.password)
            return {
                "success": result.success,
                "message": result.message or ("登录成功" if result.success else "登录失败"),
                "session_id": result.session_id,
            }
        else:
            healthy = adapter.health_check()
            return {
                "success": healthy,
                "message": "连接成功" if healthy else "连接失败",
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接异常: {str(e)}",
        }
