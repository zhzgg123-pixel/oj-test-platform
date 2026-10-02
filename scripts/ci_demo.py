"""Generate real TaskService reports against an HTTP Mock, never a C++ verdict claim."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from config_center.models import ExecutionCredentials, TaskConfig
from scripts.smoke_compose import require, validate_report
from storage.repository import TaskRepository
from task_center.service import TaskService
from tests.mock_oj.server import MockOJServer


def generate_demo(output_dir: Path, platform_sha: str) -> Path:
    require(re.fullmatch(r'[0-9a-f]{40}', platform_sha), 'full platform SHA required')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(prefix='oj-ci-') as temporary:
        root = Path(temporary)
        mock = MockOJServer()
        service = TaskService(TaskRepository(root/'tasks.db'), report_root=root/'reports',
                              platform_sha=platform_sha)
        try:
            mock.start()
            service.start()
            task_id = service.create(TaskConfig(
                base_url=mock.base_url, profile_id='a_plus_b', problem_id='1',
                strategies=['random', 'rule'], case_count=6, seed=2,
                mode='concurrent', max_workers=2, request_timeout=5,
                poll_timeout=10, poll_interval=0.1,
            ), ExecutionCredentials(username='tester', password='test-only'), name='CI HTTP Mock demo')
            task = service.wait(task_id, timeout=60)
            require(task.state == 'COMPLETED', 'demo task did not complete')
            require(task.counts['total'] == task.counts['passed'] == 6, 'demo assertions failed')
            reports = {}
            for format in ('json', 'html'):
                body = service.report_path(task_id, format).read_bytes()
                require(body and b'test-only' not in body, 'empty report or credential leak')
                if format == 'json':
                    validate_report(json.loads(body), task_id)
                path = output_dir/f'report.{format}'
                path.write_bytes(body)
                reports[format] = {'path': path.name, 'sha256': hashlib.sha256(body).hexdigest()}
            manifest = output_dir/'manifest.json'
            manifest.write_text(json.dumps({
                'schema_version': 1, 'scope': 'HTTP Mock only', 'task_id': task_id,
                'platform_sha': platform_sha, 'counts': task.counts, 'reports': reports,
            }, indent=2), encoding='utf-8')
            return manifest
        finally:
            try:
                service.close()
            finally:
                mock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--platform-sha', required=True)
    args = parser.parse_args()
    try:
        print(generate_demo(args.output_dir, args.platform_sha))
        return 0
    except Exception as exc:
        print(f'Demo FAIL: {type(exc).__name__}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
