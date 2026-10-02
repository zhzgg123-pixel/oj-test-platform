"""FastAPI application factory. Importing this module performs no runtime I/O."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from config_center.config import AppConfig
from config_center.profile_loader import ProfileLoader
from plugins.plugin_manager import PluginManager
from task_center.task_manager import TaskManager
from task_center.service import TaskService
from storage.repository import TaskRepository
from backend.routers import task_router, config_router, report_router, plugin_router


def create_app(config_path=None, db_path=None, report_dir=None, task_overrides=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.config_path = config_path
        app.state.runtime_overrides = {'db_path': db_path, 'report_dir': report_dir}
        app.state.task_overrides = task_overrides
        app.state.app_config = AppConfig.load(config_path=config_path, task_overrides=task_overrides,
                                             runtime_overrides=app.state.runtime_overrides)
        app.state.plugin_manager = PluginManager()
        settings = app.state.app_config.test
        service = TaskService(TaskRepository(settings.db_path), report_root=settings.report_dir)
        await run_in_threadpool(service.start)
        app.state.task_service = service
        app.state.task_manager = TaskManager(service=service)
        try:
            yield
        finally:
            await run_in_threadpool(service.close)

    app = FastAPI(title='OJ Test Platform API', version='0.1.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False,
                       allow_methods=['*'], allow_headers=['*'])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic hide_input_in_errors protects text, not .errors(); whitelist fields.
        details = [{k: error[k] for k in ('loc', 'msg', 'type')} for error in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': details})

    app.include_router(task_router.router, prefix='/api/tasks', tags=['tasks'])
    app.include_router(task_router.router, prefix='/api/v1/tasks', tags=['tasks-v1'])
    app.add_api_route('/reports/{filename}', report_router.get_report, methods=['GET'])
    app.include_router(config_router.router, prefix='/api/config', tags=['config'])
    app.include_router(report_router.router, prefix='/api/reports', tags=['reports'])
    app.include_router(plugin_router.router, prefix='/api/plugins', tags=['plugins'])
    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    app.mount('/frontend', StaticFiles(directory=frontend, html=True), name='frontend')

    @app.get('/api/v1/profiles')
    async def profiles():
        loader = ProfileLoader()
        result = []
        for file in sorted(loader.root.glob('*.yaml')):
            profile = loader.load(file.stem)
            result.append({'id': profile.id, 'title': profile.definition.title,
                           'profile_sha256': profile.profile_sha256})
        return {'profiles': result}

    @app.get('/api/health')
    async def health(request: Request):
        return {'status': 'ok', 'plugins': len(request.app.state.plugin_manager.list_plugins())}

    @app.get('/')
    async def root():
        return {'message': 'OJ Test Platform API', 'docs': '/docs', 'frontend': '/frontend/index.html'}

    return app


app = create_app()
