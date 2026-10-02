"""
任务管理路由

API:
- POST   /api/tasks          — 创建并运行任务
- POST   /api/tasks/generate — 仅生成用例，不执行
- GET    /api/tasks           — 任务列表
- GET    /api/tasks/{id}      — 任务详情
- POST   /api/tasks/{id}/cancel — 取消任务
- DELETE /api/tasks/{id}      — 删除任务
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from task_center.models import TaskConfig
from core_engine.case_engine.case_builder import CaseBuilder

router = APIRouter()


class GenerateCasesRequest(BaseModel):
    """仅生成用例请求"""
    problem_id: str = "1"
    strategies: list[str] = ["random", "boundary", "rule"]
    case_count: int = 5


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    name: str = "测试任务"
    adapter_name: str = "local_oj"
    base_url: str = "http://localhost:8080"
    username: str = ""
    password: str = ""
    strategies: list[str] = ["random", "boundary", "rule"]
    problem_id: str = "1"
    case_count: int = 5
    poll_interval: float = 1.0
    poll_timeout: int = 60


@router.post("/generate")
async def generate_cases(req: GenerateCasesRequest):
    """仅生成测试用例（不执行）"""
    builder = CaseBuilder()
    spec = {
        "problem_id": req.problem_id,
        "strategies": req.strategies,
        "count": req.case_count,
    }
    cases = builder.build(spec)
    return {
        "total": len(cases),
        "cases": [
            {
                "id": c.id,
                "desc": c.desc,
                "expected_status": c.expected_status,
                "tags": c.tags,
            }
            for c in cases
        ],
    }


@router.post("")
async def create_task(req: CreateTaskRequest, request: Request):
    """创建并运行任务"""
    task_manager = request.app.state.task_manager

    config = TaskConfig(
        adapter_name=req.adapter_name,
        base_url=req.base_url,
        username=req.username,
        password=req.password,
        strategies=req.strategies,
        problem_id=req.problem_id,
        case_count=req.case_count,
        poll_interval=req.poll_interval,
        poll_timeout=req.poll_timeout,
    )

    task = task_manager.create_task(config=config)
    task_manager.start_task(task.id)

    return {"task_id": task.id, "status": task.status.value}


@router.get("")
async def list_tasks(request: Request):
    """获取任务列表"""
    task_manager = request.app.state.task_manager
    tasks = task_manager.list_tasks()
    return {
        "success": True,
        "tasks": [t.to_dict() for t in tasks],
        "total": len(tasks),
    }


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request):
    """获取任务详情"""
    task_manager = request.app.state.task_manager
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {"success": True, "task": task.to_dict()}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request):
    """取消任务"""
    task_manager = request.app.state.task_manager
    ok = task_manager.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法取消任务（已完成/不存在）")
    return {"success": True, "message": "任务已取消"}


@router.delete("/{task_id}")
async def delete_task(task_id: str, request: Request):
    """删除任务"""
    task_manager = request.app.state.task_manager
    ok = task_manager.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {"success": True, "message": "任务已删除"}
