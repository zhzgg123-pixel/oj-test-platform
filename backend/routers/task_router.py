"""Task routes: merge application defaults, then validate before scheduling."""
from copy import deepcopy

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, SecretStr, ValidationError, create_model

from config_center.models import TaskConfig, ExecutionCredentials, ValidatedModel
from core_engine.case_engine.case_builder import CaseBuilder
from config_center.profile_loader import ProfileLoader

router = APIRouter()

# Optional transport fields allow application defaults to participate before
# cross-field validation. The authoritative validator remains TaskConfig.
fields = {}
for key, field in TaskConfig.model_fields.items():
    optional = deepcopy(field)
    optional.default = None
    optional.default_factory = None
    fields[key] = (field.annotation | None, optional)
TaskOverrides = create_model('TaskOverrides', __base__=ValidatedModel, **fields)


class GenerateCasesRequest(TaskOverrides):
    pass


class CreateTaskRequest(TaskOverrides):
    name: str = Field(default='测试任务', min_length=1, max_length=200)
    username: str = ''
    password: SecretStr = Field(default='', exclude=True, repr=False)


def validated_config(req, request):
    values = request.app.state.app_config.task_config().to_dict()
    values.update(req.model_dump(exclude_unset=True, exclude_none=True,
                                exclude={'name', 'username', 'password'}))
    try:
        config = TaskConfig.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors(include_input=False, include_context=False, include_url=False)) from None
    if config.mode != 'sequential':
        raise HTTPException(422, detail='concurrent mode is not enabled until S06')
    if request.app.state.plugin_manager.get_adapter(config.adapter_name) is None:
        raise HTTPException(422, detail='unknown adapter')
    try:
        ProfileLoader().load(config.profile_id)
    except ValueError:
        raise HTTPException(422, detail='invalid or missing problem profile') from None
    return config


@router.post('/generate')
async def generate_cases(req: GenerateCasesRequest, request: Request):
    config = validated_config(req, request)
    try:
        cases = CaseBuilder().build(config, ProfileLoader().load(config.profile_id))
        if not cases:
            raise ValueError('no executable cases generated')
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from None
    return {'total': len(cases), 'cases': [
        {'id': c.id, 'desc': c.desc, 'expected_status': c.expected_status, 'tags': c.tags,
         'profile_id': c.profile_id, 'profile_sha256': c.profile_sha256, 'seed': c.seed,
         'source_code': c.source_code, 'source_sha256': c.source_sha256} for c in cases]}


@router.post('', status_code=202)
async def create_task(req: CreateTaskRequest, request: Request):
    config = validated_config(req, request)
    credentials = ExecutionCredentials(username=req.username, password=req.password)
    manager = request.app.state.task_manager
    task = manager.create_task(config=config, credentials=credentials, name=req.name)
    manager.start_task(task.id)
    return {'task_id': task.id, 'status': task.status.value}


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
