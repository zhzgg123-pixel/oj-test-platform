"""Web and CLI entrypoints. Runtime resources are created only after validation."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid


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
    return result


def run_ci(args):
    from config_center.config import AppConfig
    from config_center.models import TaskConfig, ExecutionCredentials
    from core_engine.executor.task_executor import TaskExecutor
    from core_engine.report_engine.report_generator import ReportGenerator
    if args.password is not None:
        print('Use OJ_PASSWORD environment variable; --password is no longer accepted.', file=sys.stderr)
        return 2
    try:
        overrides = {key: getattr(args, key, None) for key in TaskConfig.model_fields}
        app_config = AppConfig.load(config_path=args.config, task_overrides=overrides)
        config = app_config.task_config()
        if config.mode != 'sequential':
            raise ValueError('concurrent mode is not enabled until S06')
        credentials = ExecutionCredentials(username=args.username or os.getenv('OJ_USERNAME', ''),
                                             password=os.getenv('OJ_PASSWORD', ''))
        executor = TaskExecutor()
        if executor._plugin_manager.get_adapter(config.adapter_name) is None:
            raise ValueError('unknown adapter')
    except (ValueError, OSError) as exc:
        print(f'Invalid configuration: {exc}', file=sys.stderr)
        return 2
    try:
        task_id = 'ci-' + uuid.uuid4().hex
        summary = executor.run_task(task_id, config, credentials)
        report = ReportGenerator(output_dir=args.report_dir or app_config.test.report_dir).generate(
            task_result=summary, task_config=config.to_dict())
        result = {'total': summary.total, 'passed': summary.passed, 'failed': summary.failed,
                  'error': summary.error, 'pass_rate': summary.pass_rate, 'duration': summary.duration}
        if args.output:
            Path(args.output).write_text(json.dumps({'ci_run': True, 'task_id': task_id,
                'config': config.to_dict(), 'result': result, 'reports': report},
                ensure_ascii=False, indent=2), encoding='utf-8')
        status = cli_exit_code(summary)
        print(json.dumps(result, ensure_ascii=False))
        print('CI passed' if status == 0 else 'CI failed')
        return status
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f'Execution failed: {type(exc).__name__}', file=sys.stderr)
        return 1


def run_server(args):
    from backend.app import create_app
    import uvicorn
    uvicorn.run(create_app(config_path=args.config), host=args.host, port=args.port, log_level=args.log_level)
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    return run_ci(args) if args.ci else run_server(args)


if __name__ == '__main__':
    raise SystemExit(main())
