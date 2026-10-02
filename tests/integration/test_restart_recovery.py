"""Real process ownership and recovery; no shared developer database."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.helpers import wait_until
from storage.repository import TaskRepository

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration
OWNER = '''
import json, sys
from pathlib import Path
from config_center.models import TaskConfig
from config_center.profile_loader import ProfileLoader
from core_engine.case_engine.case_builder import CaseBuilder
from storage.repository import TaskRepository
from task_center.runtime import ExecutionLease
repo = TaskRepository(sys.argv[1])
lease = ExecutionLease(repo)
lease.start()
config = TaskConfig(case_count=3)
profile = ProfileLoader().load(config.profile_id)
task_id = repo.insert_task(config, profile, CaseBuilder().build(config, profile), 'child-sha', None)
repo.transition(task_id, {'PENDING'}, 'RUNNING')
Path(sys.argv[2]).write_text(json.dumps({'task_id': task_id}), encoding='utf-8')
sys.stdin.read(1)
lease.close()
'''
PROBE = '''
import sys
from storage.repository import TaskRepository
from task_center.runtime import ExecutionLease, RuntimeBusyError
repo = TaskRepository(sys.argv[1])
lease = ExecutionLease(repo)
try:
    lease.start()
except RuntimeBusyError:
    print('BUSY:' + repo.get_task(sys.argv[2]).state)
    sys.exit(2)
print(repo.get_task(sys.argv[2]).state)
lease.close()
'''


@pytest.mark.parametrize('shutdown', ['graceful', 'killed'])
def test_second_process_cannot_recover_live_owner_but_can_after_exit(tmp_path, shutdown):
    db = tmp_path / 'tasks.db'
    ready = tmp_path / 'ready.json'
    owner = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', OWNER, str(db), str(ready)],
                             cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_until(lambda: ready.exists() or owner.poll() is not None, timeout=10)
        if not ready.exists():
            raise AssertionError(owner.communicate(timeout=5)[1].decode())
        task_id = json.loads(ready.read_text())['task_id']
        # A separate process may query, but must not mutate/recover another owner's task.
        probe = subprocess.run([sys.executable, '-X', 'utf8', '-c', PROBE, str(db), task_id],
                               cwd=ROOT, capture_output=True, text=True, timeout=10)
        assert probe.returncode == 2, probe.stderr
        assert probe.stdout.strip() == 'BUSY:RUNNING'
        assert TaskRepository(db).get_task(task_id).state == 'RUNNING'
        if shutdown == 'killed':
            owner.kill()
            owner.communicate(timeout=10)
        else:
            owner.communicate(input=b'x', timeout=10)
            assert owner.returncode == 0
        recovered = subprocess.run([sys.executable, '-X', 'utf8', '-c', PROBE, str(db), task_id],
                                   cwd=ROOT, capture_output=True, text=True, timeout=10)
        assert recovered.returncode == 0, recovered.stderr
        assert recovered.stdout.strip() == 'INTERRUPTED'
        assert TaskRepository(db).get_task(task_id).counts['error'] == 3
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.communicate(timeout=10)


def test_same_process_second_lease_fails_and_close_is_idempotent(tmp_path):
    from task_center.runtime import ExecutionLease, RuntimeBusyError
    repo = TaskRepository(tmp_path / 'tasks.db')
    a, b = ExecutionLease(repo), ExecutionLease(repo)
    a.start()
    try:
        with pytest.raises(RuntimeBusyError):
            b.start()
        a.start()  # Idempotent start of the actual owner.
    finally:
        a.close(); a.close()
    b.start(); b.close()


def test_failed_start_releases_os_lock(tmp_path, monkeypatch):
    from task_center.runtime import ExecutionLease
    repo = TaskRepository(tmp_path / 'tasks.db')
    def fail():
        raise ValueError('migration failure')
    with monkeypatch.context() as patch:
        patch.setattr(repo, 'initialize', fail)
        with pytest.raises(ValueError):
            ExecutionLease(repo).start()
    lease = ExecutionLease(repo)
    lease.start(); lease.close()
