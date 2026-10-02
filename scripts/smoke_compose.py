"""HTTP-only demo acceptance. No real C++ verdict claim; failures exit nonzero."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_report(report, task_id):
    require(report['task']['id'] == task_id, 'report belongs to a different task')
    require(re.fullmatch(r'[0-9a-f]{40}', report['task']['platform_sha']) is not None,
            'report must identify a full source commit')
    cases = report['all_cases']
    require(len(cases) == 6, 'expected six demo cases')
    require(all(c['status'] == 'PASSED' for c in cases), 'a demo assertion did not pass')
    require(any(c['expectation']['kind'] == c['observation']['kind'] == 'verdict' and
                c['expectation']['verdict'] == c['observation']['verdict'] == 'AC'
                for c in cases), 'missing expected AC')
    require(any(c['expectation']['kind'] == c['observation']['kind'] == 'http_error' and
                c['expectation']['http_status'] == c['observation']['http_status'] == 401
                for c in cases), 'missing expected rejection')


def run(phase, platform_url, evidence, mock_url, timeout):
    deadline = time.monotonic() + timeout
    base = platform_url.rstrip('/')

    def request(path, payload=None):
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'smoke deadline exceeded')
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(base + path, data=body, headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=min(5, remaining)) as response:
            return response.status, response.headers.get_content_type(), response.read()

    status, _, body = request('/api/health')
    require(status == 200 and json.loads(body)['status'] == 'ok', 'platform unhealthy')
    saved = None
    if phase == 'create':
        require(not evidence.exists(), 'evidence already exists; use verify or a new evidence path')
        status, _, body = request('/api/v1/tasks', {
            'name': 'Docker demo acceptance', 'base_url': mock_url,
            'username': 'tester', 'password': 'test-only',
            'profile_id': 'a_plus_b', 'problem_id': '1', 'strategies': ['random', 'rule'],
            'case_count': 6, 'seed': 2, 'mode': 'concurrent', 'max_workers': 2,
            'request_timeout': 5, 'poll_timeout': 10, 'poll_interval': 0.1,
        })
        require(status == 202, 'task creation must return 202')
        task_id = json.loads(body)['task_id']
    else:
        saved = json.loads(evidence.read_text(encoding='utf-8'))
        task_id = saved['task_id']
    while True:
        _, _, body = request(f'/api/v1/tasks/{task_id}')
        task = json.loads(body)['task']
        if task['state'] in {'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            break
        require(time.monotonic() < deadline, 'task did not reach a terminal state')
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    require(task['state'] == 'COMPLETED' and task['success'], 'task did not succeed')
    require(task['counts']['total'] == task['counts']['passed'] == 6, 'invalid task counts')
    hashes = {}
    for format, content_type in [('json', 'application/json'), ('html', 'text/html')]:
        _, actual_type, body = request(f'/api/v1/tasks/{task_id}/reports/{format}')
        require(actual_type == content_type and bool(body), 'invalid report download')
        require(b'test-only' not in body, 'demo credential leaked into report')
        if format == 'json':
            report = json.loads(body)
            validate_report(report, task_id)
            require(report['task']['platform_sha'] == task['platform_sha'],
                    'report and task source versions differ')
        else:
            require(task_id.encode() in body, 'HTML missing task identity')
        hashes[format] = hashlib.sha256(body).hexdigest()
    result = {'schema_version': 1, 'scope': 'HTTP Mock only', 'task_id': task_id,
              'platform_sha': task['platform_sha'], 'counts': task['counts'], 'report_sha256': hashes}
    if saved is not None:
        require(result == saved, 'persisted task or report changed after restart')
    else:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['create', 'verify'], required=True)
    parser.add_argument('--platform-url', default='http://platform:8000')
    parser.add_argument('--mock-url', default='http://mock-oj:8099')
    parser.add_argument('--evidence', type=Path, default=Path('/evidence/smoke.json'))
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    try:
        require(0 < args.timeout <= 300, 'timeout must be in (0, 300]')
        result = run(args.phase, args.platform_url, args.evidence, args.mock_url, args.timeout)
        print(json.dumps({'phase': args.phase, 'status': 'PASS', **result}))
        return 0
    except Exception as exc:
        # Avoid printing HTTP payloads or request credentials.
        print(f'Smoke FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
