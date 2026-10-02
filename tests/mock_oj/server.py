"""A deterministic HTTP test service matching cpp-oj's synchronous protocol.

Source: cpp-oj 84ded72d, src/main.cpp and src/middleware/auth.cpp.
Verdicts are selected by explicit test markers, never by executing C++.
"""
from __future__ import annotations

import argparse
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
import threading
from urllib.parse import parse_qs, urlsplit
import uuid


class MockOJServer:
    SCENARIOS = {'all-verdicts', 'login-rejected', 'problem-not-found', 'malformed', 'slow', 'disconnect'}

    def __init__(self, scenario='all-verdicts', delay=0.3, get_statuses=None, submit_status=200):
        if scenario not in self.SCENARIOS:
            raise ValueError(f'unknown Mock OJ scenario: {scenario}')
        if delay < 0:
            raise ValueError('delay must be non-negative')
        self.scenario = scenario
        self.delay = delay
        self.get_statuses = list(get_statuses or [])
        self.submit_status = submit_status
        self._lock = threading.Lock()
        self._release = threading.Event()
        self._release.set()
        self._stop = threading.Event()
        self._requests = []
        self._sessions = set()
        self._active = 0
        self._max_active = 0
        self._httpd = None
        self._thread = None
        self.base_url = ''

    @property
    def requests(self):
        with self._lock:
            return [dict(record) for record in self._requests]

    @property
    def max_active_submissions(self):
        with self._lock:
            return self._max_active

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def block_submissions(self):
        self._release.clear()

    def release_submissions(self):
        self._release.set()

    def start(self, host='127.0.0.1', port=0):
        if self._httpd is not None:
            raise RuntimeError('server is already started')
        self._stop.clear()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # No headers, credentials or arbitrary request text in stderr.

            def reply(self, status, data, cookie=None, malformed=False, location=None):
                payload = b'{invalid json' if malformed else json.dumps(data).encode('utf-8')
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(payload)))
                    if location:
                        self.send_header('Location', location)
                    if cookie:
                        self.send_header('Set-Cookie', f'session_id={cookie}; Path=/; HttpOnly')
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # Expected when a test deliberately times out.

            def fields(self):
                size = int(self.headers.get('Content-Length', '0'))
                if size > 1024 * 1024:
                    raise ValueError('request body too large')
                body = self.rfile.read(size).decode('utf-8')
                if 'application/json' in self.headers.get('Content-Type', ''):
                    result = json.loads(body)
                    if not isinstance(result, dict):
                        raise ValueError('object required')
                    return result
                return {k: v[-1] for k, v in parse_qs(body, keep_blank_values=True).items()}

            def record(self, fields):
                cookies = SimpleCookie()
                cookies.load(self.headers.get('Cookie', ''))
                value = cookies['session_id'].value if 'session_id' in cookies else ''
                path = urlsplit(self.path).path
                with owner._lock:
                    authenticated = value in owner._sessions
                    owner._requests.append({
                        'method': self.command, 'path': path,
                        'authenticated': authenticated, 'cookie_present': bool(value),
                        'session_fingerprint': hashlib.sha256(value.encode()).hexdigest() if value else None,
                        'code_sha256': hashlib.sha256(str(fields.get('code', '')).encode()).hexdigest(),
                    })
                return path, authenticated

            def do_GET(self):
                path, _ = self.record({})
                with owner._lock:
                    status = owner.get_statuses.pop(0) if owner.get_statuses else 200
                if status != 200:
                    self.reply(status, {'error': 'Injected HTTP failure'})
                    return
                if path in ('/', '/health'):
                    self.reply(200, {'status': 'ok', 'mock': True})
                elif path == '/api/problems':
                    self.reply(200, {'problems': [{'id': 1, 'title': 'A plus B'}, {'id': 2, 'title': 'Max of two'}]})
                else:
                    self.reply(404, {'error': 'Not found'})

            def do_POST(self):
                try:
                    fields = self.fields()
                except (ValueError, UnicodeError):
                    self.reply(400, {'error': 'Invalid request body'})
                    return
                path, authenticated = self.record(fields)
                if path == '/api/login':
                    valid = (fields.get('username') == 'tester' and fields.get('password') == 'test-only'
                             and owner.scenario != 'login-rejected')
                    if not valid:
                        self.reply(200, {'success': False, 'message': 'Invalid credentials'})
                        return
                    session = uuid.uuid4().hex
                    with owner._lock:
                        owner._sessions.add(session)
                    self.reply(200, {'success': True}, cookie=session)
                    return
                match = re.fullmatch(r'/api/submit/(\d+)', path)
                if not match:
                    self.reply(404, {'error': 'Not found'})
                    return
                if not authenticated:
                    self.reply(401, {'success': False, 'error': 'Not authenticated'})
                    return
                if owner.submit_status != 200:
                    self.reply(owner.submit_status, {'error': 'Injected HTTP failure'},
                               location='/api/submit/2' if owner.submit_status in {307, 308} else None)
                    return
                code = fields.get('code', '')
                if not code:
                    self.reply(200, {'success': False, 'error': 'Code is required'})
                    return
                if match[1] not in {'1', '2'} or owner.scenario == 'problem-not-found':
                    self.reply(200, {'success': False, 'error': 'Problem not found'})
                    return
                with owner._lock:
                    owner._active += 1
                    owner._max_active = max(owner._max_active, owner._active)
                try:
                    if not owner._release.wait(timeout=5):
                        self.reply(503, {'error': 'Mock barrier deadline exceeded'})
                        return
                    if owner.scenario == 'slow':
                        owner._stop.wait(owner.delay)
                    if owner.scenario == 'disconnect':
                        self.close_connection = True
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    verdict_match = re.search(r'//\s*verdict:(AC|WA|CE|TLE|RE)\b', str(code))
                    verdict = verdict_match[1] if verdict_match else 'AC'
                    self.reply(200, {
                        'result': verdict, 'passed': 2 if verdict == 'AC' else 0, 'total': 2,
                        'time_ms': None if verdict == 'CE' else 1,
                        'memory_kb': None if verdict == 'CE' else 64,
                        'compile_error': 'mock compilation error' if verdict == 'CE' else None,
                        'detail': 'Compilation Error' if verdict == 'CE' else f'Mock {verdict}',
                    }, malformed=owner.scenario == 'malformed')
                finally:
                    with owner._lock:
                        owner._active -= 1

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = False
        self._httpd.block_on_close = True
        address, assigned_port = self._httpd.server_address
        self.base_url = f'http://{address}:{assigned_port}'
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        kwargs={'poll_interval': 0.05}, name='mock-oj-listener')
        self._thread.start()
        return self

    def close(self):
        if self._httpd is None:
            return
        self._stop.set()
        self.release_submissions()
        self._httpd.shutdown()
        self._httpd.server_close()  # Join request threads after releasing their waits.
        self._thread.join(timeout=2)
        if self._thread.is_alive():
            raise RuntimeError('Mock OJ listener did not stop')
        self._httpd = None
        self._thread = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--scenario', choices=sorted(MockOJServer.SCENARIOS), default='all-verdicts')
    args = parser.parse_args()
    server = MockOJServer(args.scenario).start(args.host, args.port)
    print(f'Mock OJ listening at {server.base_url}', flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == '__main__':
    main()
