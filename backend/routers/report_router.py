"""Report aliases backed by stored task metadata, plus safe legacy file reads."""
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core_engine.report_engine.report_generator import ReportGenerator
from backend.routers.task_router import service_call

router = APIRouter()


@router.get('')
def list_reports(request: Request):
    service = request.app.state.task_service
    reports = []
    for row in service.repo.list_reports():
        size = None
        try:
            size = service.report_path(row['task_id'], row['format']).stat().st_size
        except (KeyError, OSError, ValueError):
            pass  # Keep missing/corrupt metadata visible; downloads still reject it.
        reports.append({'filename': f"{row['task_id']}.{row['format']}", 'format': row['format'],
                        'task_id': row['task_id'], 'created_at': row['created_at'], 'size': size,
                        'available': size is not None, 'path': f"reports/{row['task_id']}.{row['format']}"})
    # Preserve flat reports from releases before durable tasks were introduced.
    reports.extend(ReportGenerator(service.report_root).list_reports())
    return {'success': True, 'reports': reports, 'total': len(reports)}


@router.get('/{filename}')
def get_report(filename: str, request: Request):
    service = request.app.state.task_service
    task_id, _, format = filename.rpartition('.')
    if format not in {'json', 'html'} or Path(filename).name != filename or '\\' in filename or ':' in filename:
        raise HTTPException(422, detail='Invalid report name')
    try:
        UUID(task_id)
    except ValueError:
        path = (service.report_root / filename).resolve()
        if not path.is_relative_to(service.report_root):
            raise HTTPException(422, detail='Invalid report path')
        if not path.is_file():
            raise HTTPException(404, detail='Report not found')
    else:
        path = service_call(lambda: service.report_path(task_id, format))
    return FileResponse(path, media_type='application/json' if format == 'json' else 'text/html')
