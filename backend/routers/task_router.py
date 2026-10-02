"""Task routes: merge application defaults, then validate before scheduling."""
from copy import deepcopy
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse
from task_center.service import QueueFullError, TaskConflictError
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
def generate_cases(req: GenerateCasesRequest, request: Request):
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


def service_call(operation):
    try:
        return operation()
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, detail='Task or report not found') from None
    except TaskConflictError as exc:
        raise HTTPException(409, detail=str(exc)) from None
    except QueueFullError as exc:
        raise HTTPException(429, detail=str(exc)) from None
    except ValueError:
        raise HTTPException(422, detail='Invalid task or report data') from None


@router.post('', status_code=202)
def create_task(req: CreateTaskRequest, request: Request):
    config = validated_config(req, request)
    credentials = ExecutionCredentials(username=req.username, password=req.password)
    service = request.app.state.task_service
    task_id = service_call(lambda: service.create(config, credentials, name=req.name))
    return {'task_id': task_id, 'status': service.get(task_id).state}


@router.get('')
def list_tasks(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    service = request.app.state.task_service
    tasks = service.repo.list_tasks(limit, offset)
    return {'success': True, 'tasks': [service.serialize_task(task.id) for task in tasks],
            'total': service.repo.count_tasks(), 'limit': limit, 'offset': offset}


@router.get('/{task_id}')
def get_task(task_id: str, request: Request):
    service = request.app.state.task_service
    return {'success': True, 'task': service_call(lambda: service.serialize_task(task_id))}


@router.get('/{task_id}/cases')
def get_cases(task_id: str, request: Request):
    cases = service_call(lambda: request.app.state.task_service.repo.list_cases(task_id))
    return {'success': True, 'cases': [asdict(case) for case in cases], 'total': len(cases)}


@router.get('/{task_id}/reports/{format}')
def get_report(task_id: str, format: Literal['json', 'html'], request: Request):
    path = service_call(lambda: request.app.state.task_service.report_path(task_id, format))
    return FileResponse(path, media_type='application/json' if format == 'json' else 'text/html')


@router.post('/{task_id}/cancel')
def cancel_task(task_id: str, request: Request):
    service_call(lambda: request.app.state.task_service.cancel(task_id))
    return {'success': True, 'message': 'Cancellation accepted'}


@router.delete('/{task_id}')
def delete_task(task_id: str, request: Request):
    service_call(lambda: request.app.state.task_service.delete(task_id))
    return {'success': True, 'message': 'Task deleted'}
