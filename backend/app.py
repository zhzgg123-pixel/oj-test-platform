"""FastAPI application factory. Importing this module performs no runtime I/O."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from config_center.config import AppConfig
from config_center.profile_loader import ProfileLoader
from plugins.plugin_manager import PluginManager
from task_center.task_manager import TaskManager
from backend.routers import task_router, config_router, report_router, plugin_router


def create_app(config_path=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.config_path = config_path
        app.state.app_config = AppConfig.load(config_path=config_path)
        app.state.plugin_manager = PluginManager()
        app.state.task_manager = TaskManager(report_dir=app.state.app_config.test.report_dir)
        report_mount = Mount('/reports', app=StaticFiles(directory=app.state.app_config.test.report_dir), name='reports')
        app.router.routes.append(report_mount)
        try:
            yield
        finally:
            try:
                app.state.task_manager.close()
            finally:
                app.router.routes.remove(report_mount)

    app = FastAPI(title='OJ Test Platform API', version='0.1.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False,
                       allow_methods=['*'], allow_headers=['*'])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic hide_input_in_errors protects text, not .errors(); whitelist fields.
        details = [{k: error[k] for k in ('loc', 'msg', 'type')} for error in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': details})

    app.include_router(task_router.router, prefix='/api/tasks', tags=['tasks'])
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
