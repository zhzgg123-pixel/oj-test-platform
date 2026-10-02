"""Explicitly opted-in real OJ fixtures with retained evidence and exact cleanup."""
from dataclasses import asdict
import hashlib
import json
import threading
import time
import uuid

import pytest

from config_center.models import ExecutionCredentials, TaskConfig
from config_center.profile_loader import ProfileLoader
from core_engine.case_engine.case_builder import CaseBuilder
from plugins.local_oj.adapter import LocalOJAdapter
from scripts.e2e_environment import private_settings
from scripts.e2e_fixtures import seed, cleanup
from scripts.prepare_e2e import ROOT
from storage.repository import TaskRepository
from task_center.service import TaskService


@pytest.fixture(scope='session')
def real_oj_environment(pytestconfig):
    config = pytestconfig.getoption('--e2e-config')
    root = ROOT/'artifacts'/'e2e'/uuid.uuid4().hex
    root.mkdir(parents=True)
    ledger_path = root/'fixtures.json'
    try:
        ledger = seed(config, ledger_path)
        (root/'fixtures-created.json').write_text(json.dumps(ledger, indent=2)+'\n', encoding='utf-8')
        for entry in ledger['problems']:
            assert entry['profile_sha256'] == ProfileLoader().load(entry['profile_id']).profile_sha256
        yield root, ledger
    finally:
        if ledger_path.exists():
            cleanup(config, ledger_path)  # Teardown failure makes the E2E run fail.


class RealRunner:
    def __init__(self, root, ledger):
        self.root, self.ledger = root, ledger
        self.scope = ledger['scope']
        self.entries = {entry['profile_id']: entry for entry in ledger['problems']}
        self.credentials = ExecutionCredentials(username='e2e_admin',
            password=private_settings()['E2E_ADMIN_PASSWORD'])
        self.lock = threading.Lock()
        self.requests = []
        self.logins = []
        runner = self

        class TracedRealAdapter(LocalOJAdapter):
            """Observe real calls without barriers, retries or response replacement."""
            def __init__(self, base_url, timeout=30):
                super().__init__(base_url, timeout)
                self.trace_id = uuid.uuid4().hex

            def login(self, username, password):
                result = super().login(username, password)
                with runner.lock:
                    runner.logins.append({'adapter_id': self.trace_id, 'success': result.success,
                        'session_sha256': hashlib.sha256(result.session_id.encode()).hexdigest()
                        if result.success else None})
                return result

            def submit_code(self, problem_id, code, lang='cpp'):
                entry = {'adapter_id': self.trace_id, 'problem_id': problem_id,
                         'source_sha256': hashlib.sha256(code.encode()).hexdigest(),
                         'started': time.monotonic(), 'finished': None}
                with runner.lock:
                    runner.requests.append(entry)
                try:
                    return super().submit_code(problem_id, code, lang)
                finally:
                    with runner.lock:
                        entry['finished'] = time.monotonic()

        self.service = TaskService(TaskRepository(root/'tasks.db'), report_root=root/'reports',
            sut_sha=self.scope['sut_sha'],
            adapter_factory=lambda name, url, timeout: TracedRealAdapter(url, timeout))
        self.service.start()

    def config(self, profile_id, mode, **kwargs):
        values = dict(base_url=self.scope['base_url'], profile_id=profile_id,
                          problem_id=str(self.entries[profile_id]['problem_id']),
                          mode=mode, max_workers=3, strategies=['random'], case_count=1,
                          request_timeout=30)
        values.update(kwargs)
        return TaskConfig(**values)

    def select_seed(self, config, predicate):
        profile = ProfileLoader().load(config.profile_id)
        for seed_value in range(1000):
            candidate = config.model_copy(update={'seed': seed_value})
            if predicate(CaseBuilder().build(candidate, profile)):
                return candidate
        raise AssertionError('could not select required deterministic template coverage')

    def start(self, config, credentials=None):
        return self.service.create(config, credentials or self.credentials)

    def finish(self, task_id):
        task = self.service.wait(task_id, timeout=90)
        cases = self.service.repo.list_cases(task_id)
        assert len(cases) == task.counts['total']
        assert task.sut_sha == self.scope['sut_sha']
        assert all(c.result is not None and c.source_sha256 == hashlib.sha256(c.input['code'].encode()).hexdigest()
                   for c in cases)
        evidence = {'task': asdict(task), 'cases': [asdict(c) for c in cases]}
        (self.root/(task_id+'.json')).write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
        if task.state in {'COMPLETED', 'CANCELLED'}:
            report = json.loads(self.service.report_path(task_id, 'json').read_text(encoding='utf-8'))
            assert report['task']['sut_sha'] == task.sut_sha
            assert report['summary']['total'] == task.counts['total']
            assert len(report['all_cases']) == len(cases)
            assert self.service.report_path(task_id, 'html').stat().st_size > 0
        return task, cases

    def run_verdict(self, profile_id, mode, verdict):
        config = self.select_seed(self.config(profile_id, mode),
                                  lambda cases: cases[0].expectation.verdict == verdict)
        return self.finish(self.start(config))

    def close(self):
        try:
            self.service.close(timeout=60)
        finally:
            (self.root/'http-trace.json').write_text(json.dumps({
                'requests': self.requests, 'logins': self.logins}, indent=2)+'\n', encoding='utf-8')


@pytest.fixture
def real_oj_runner(real_oj_environment, request):
    root, ledger = real_oj_environment
    # Long parameterized node names exceed Windows paths once task/report UUIDs
    # and atomic-publication suffixes are appended. Keep the full name in metadata.
    directory = root/hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:12]
    directory.mkdir()
    (directory/'test-node.json').write_text(json.dumps({'nodeid': request.node.nodeid})+'\n', encoding='utf-8')
    runner = RealRunner(directory, ledger)
    try:
        yield runner
    finally:
        runner.close()
