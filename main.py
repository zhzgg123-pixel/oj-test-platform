"""Web and CLI entrypoints. Runtime resources are created only after validation."""
import argparse
import json
import os
from pathlib import Path
import sys


def cli_exit_code(summary):
    return 0 if (summary.total > 0 and summary.passed == summary.total
                 and summary.failed == 0 and summary.error == 0) else 1


def parser():
    result = argparse.ArgumentParser(description='OJ Test Platform')
    result.add_argument('--host', default='127.0.0.1')
    result.add_argument('--port', type=int, default=8000)
    result.add_argument('--config')
    result.add_argument('--log-level', default='info')
    result.add_argument('--ci', action='store_true')
    result.add_argument('--problem', '--problem-id', dest='problem_id')
    result.add_argument('--profile', dest='profile_id')
    result.add_argument('--strategies', nargs='*')
    result.add_argument('--count', '--case-count', dest='case_count', type=int)
    result.add_argument('--base-url')
    result.add_argument('--adapter-name')
    result.add_argument('--mode', choices=['sequential', 'concurrent'])
    result.add_argument('--max-workers', type=int)
    result.add_argument('--seed', type=int)
    result.add_argument('--timeout', dest='request_timeout', type=float)
    result.add_argument('--poll-interval', type=float)
    result.add_argument('--poll-timeout', type=float)
    result.add_argument('--username')
    result.add_argument('--password', help=argparse.SUPPRESS)
    result.add_argument('--output')
    result.add_argument('--report-dir')
    result.add_argument('--db', dest='db_path')
    return result


def task_overrides(args):
    from config_center.models import TaskConfig
    return {key: getattr(args, key, None) for key in TaskConfig.model_fields}


def run_ci(args):
    from config_center.config import AppConfig
    from config_center.profile_loader import ProfileLoader
    from config_center.models import ExecutionCredentials
    from plugins.plugin_manager import PluginManager
    from storage.repository import TaskRepository
    from task_center.service import TaskService
    from task_center.runtime import RuntimeBusyError
    if args.password is not None:
        print('Use OJ_PASSWORD environment variable; --password is no longer accepted.', file=sys.stderr)
        return 2
    try:
        app_config = AppConfig.load(config_path=args.config, task_overrides=task_overrides(args),
                                    runtime_overrides={'db_path': args.db_path, 'report_dir': args.report_dir})
        config = app_config.task_config()
        ProfileLoader().load(config.profile_id)
        if config.mode != 'sequential':
            raise ValueError('concurrent mode is not enabled until S06')
        credentials = ExecutionCredentials(username=args.username or os.getenv('OJ_USERNAME', ''),
                                             password=os.getenv('OJ_PASSWORD', ''))
        if PluginManager().get_adapter(config.adapter_name) is None:
            raise ValueError('unknown adapter')
    except (ValueError, OSError) as exc:
        print(f'Invalid configuration: {exc}', file=sys.stderr)
        return 2
    service = TaskService(TaskRepository(app_config.test.db_path), report_root=app_config.test.report_dir)
    task_id = None
    try:
        service.start()
        task_id = service.create(config, credentials, name='CLI regression')
        while True:
            try:
                task = service.wait(task_id, timeout=1)
                break
            except TimeoutError:
                continue
        summary = service.task_result(task_id)
        result = {'total': summary.total, 'passed': summary.passed, 'failed': summary.failed,
                  'error': summary.error, 'cancelled': summary.cancelled,
                  'pass_rate': summary.pass_rate, 'duration': summary.duration}
        reports = {r['format'] + '_path': str(service.report_root / r['relative_path'])
                   for r in service.repo.list_reports(task_id)}
        if args.output:
            Path(args.output).write_text(json.dumps({'ci_run': True, 'task_id': task_id, 'state': task.state,
                'config': config.to_dict(), 'result': result, 'reports': reports},
                ensure_ascii=False, indent=2), encoding='utf-8')
        status = 0 if service.success(task_id) else 1
        print(json.dumps({'task_id': task_id, 'state': task.state, **result}, ensure_ascii=False))
        print('CI passed' if status == 0 else 'CI failed')
        return status
    except RuntimeBusyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        if task_id is not None:
            from storage.repository import ACTIVE
            if service.get(task_id).state in ACTIVE:
                service.cancel(task_id)
        return 130
    except Exception as exc:
        print(f'Execution failed: {type(exc).__name__}', file=sys.stderr)
        return 1
    finally:
        try:
            service.close()
        except TimeoutError:
            print('Shutdown deadline exceeded; unfinished task will be recovered on next start.', file=sys.stderr)


def run_server(args):
    from backend.app import create_app
    import uvicorn
    uvicorn.run(create_app(config_path=args.config, db_path=args.db_path, report_dir=args.report_dir,
                           task_overrides=task_overrides(args)), host=args.host, port=args.port, log_level=args.log_level)
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    return run_ci(args) if args.ci else run_server(args)


if __name__ == '__main__':
    raise SystemExit(main())
