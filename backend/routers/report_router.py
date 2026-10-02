"""
报告查询路由

API:
- GET  /api/reports          — 报告列表
- GET  /api/reports/{filename} — 获取报告内容
"""

from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core_engine.report_engine.report_generator import ReportGenerator

router = APIRouter()


@router.get("")
async def list_reports(request: Request):
    """列出所有报告"""
    app_config = request.app.state.app_config
    gen = ReportGenerator(output_dir=app_config.test.report_dir)
    reports = gen.list_reports()
    return {"success": True, "reports": reports, "total": len(reports)}


@router.get("/{filename}")
async def get_report(filename: str, request: Request):
    """获取报告内容"""
    app_config = request.app.state.app_config
    report_dir = Path(app_config.test.report_dir)
    filepath = report_dir / filename

    # 安全检查：防止路径遍历
    try:
        filepath = filepath.resolve()
        report_dir = report_dir.resolve()
        if not str(filepath).startswith(str(report_dir)):
            raise HTTPException(status_code=400, detail="非法路径")
    except Exception:
        raise HTTPException(status_code=400, detail="非法路径")

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"报告不存在: {filename}")

    content = filepath.read_text(encoding="utf-8")

    if filename.endswith(".json"):
        return JSONResponse(content=json.loads(content))
    elif filename.endswith(".html"):
        return HTMLResponse(content=content)
    else:
        return {"success": True, "content": content}
