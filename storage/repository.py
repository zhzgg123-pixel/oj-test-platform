"""Immutable task snapshots and idempotent results; no network or credentials here."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import time
from uuid import uuid4

from config_center.models import TaskConfig
from core_engine.case_engine.base_generator import TestCase
from core_engine.contracts import Expectation
from .database import Database

ACTIVE = {'PENDING', 'RUNNING', 'CANCEL_REQUESTED'}
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}
TRANSITIONS = {
    'PENDING': {'RUNNING', 'CANCELLED', 'FAILED', 'INTERRUPTED'},
    'RUNNING': {'COMPLETED', 'FAILED', 'CANCEL_REQUESTED', 'INTERRUPTED'},
    'CANCEL_REQUESTED': {'CANCELLED', 'FAILED', 'INTERRUPTED'},
}
CASE_STATES = ('PENDING', 'RUNNING', 'PASSED', 'FAILED', 'ERROR', 'CANCELLED')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def source_hash(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def case_input(case):
    value = asdict(case)
    value.pop('expectation')
    # Persist generator provenance, never arbitrary plugin runtime metadata.
    value['metadata'] = {k: v for k, v in case.metadata.items()
                         if k in {'generator', 'seed', 'template_path', 'profile_id', 'profile_sha256', 'ordinal'}}
    return value


@dataclass(frozen=True)
class TaskRecord:
    id: str
    state: str
    config: dict
    profile: dict
    profile_sha256: str
    platform_sha: str
    sut_sha: str | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    error: dict | None
    counts: dict


@dataclass(frozen=True)
class StoredCase:
    id: str
    task_id: str
    ordinal: int
    strategy: str
    input: dict
    expectation: dict
    source_sha256: str
    state: str
    result: dict | None

    def to_case(self):
        if source_hash(self.input['code']) != self.source_sha256:
            raise ValueError('stored source hash mismatch')
        return TestCase(**self.input, expectation=Expectation(**self.expectation))


class TaskRepository:
    def __init__(self, db_path):
        self.db_path = Path(db_path).resolve()
        self.database = Database(self.db_path)

    def initialize(self):
        self.database.initialize()

    def insert_task(self, config, profile, cases, platform_sha, sut_sha):
        if not isinstance(config, TaskConfig):
            raise TypeError('validated TaskConfig required')
        if len(cases) != config.case_count:
            raise ValueError('case count does not match config')
        if profile.id != config.profile_id:
            raise ValueError('profile mismatch')
        snapshots = []
        for ordinal, case in enumerate(cases):
            if source_hash(case.code) != case.source_sha256:
                raise ValueError('source hash mismatch')
            if case.profile_sha256 != profile.profile_sha256 or case.profile_id != config.profile_id:
                raise ValueError('case profile mismatch')
            expected = case.expectation or Expectation(kind='verdict', verdict=case.expected_status)
            snapshots.append((str(uuid4()), ordinal, case, encode(case_input(case)), encode(asdict(expected))))
        task_id = str(uuid4())
        with self.database.connection(write=True) as db:
            db.execute('INSERT INTO tasks(id,state,config_json,profile_json,profile_sha256,platform_sha,sut_sha,created_at) VALUES (?,?,?,?,?,?,?,?)',
                       (task_id, 'PENDING', encode(config.to_dict()), encode(profile.to_dict()), profile.profile_sha256, platform_sha, sut_sha, time.time()))
            for case_id, ordinal, case, actual, expected in snapshots:
                db.execute('INSERT INTO task_cases VALUES (?,?,?,?,?,?,?,?,?)',
                           (case_id, task_id, case.id, ordinal, case.strategy, actual, expected, case.source_sha256, 'PENDING'))
        return task_id

    @staticmethod
    def _required(db, task_id):
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return row

    def _record(self, db, row):
        counts = {state.lower(): 0 for state in CASE_STATES}
        for item in db.execute('SELECT state,count(*) AS n FROM task_cases WHERE task_id=? GROUP BY state', (row['id'],)):
            counts[item['state'].lower()] = item['n']
        counts['total'] = sum(counts.values())
        return TaskRecord(row['id'], row['state'], json.loads(row['config_json']), json.loads(row['profile_json']),
                          row['profile_sha256'], row['platform_sha'], row['sut_sha'], row['created_at'],
                          row['started_at'], row['finished_at'], json.loads(row['error_json']) if row['error_json'] else None, counts)

    def get_task(self, task_id):
        with self.database.connection() as db:
            return self._record(db, self._required(db, task_id))

    def list_tasks(self, limit=20, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError('invalid pagination')
        with self.database.connection() as db:
            rows = db.execute('SELECT * FROM tasks ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
            return [self._record(db, row) for row in rows]

    def list_cases(self, task_id):
        with self.database.connection() as db:
            self._required(db, task_id)
            cases = []
            for row in db.execute('SELECT * FROM task_cases WHERE task_id=? ORDER BY ordinal', (task_id,)):
                result = db.execute('SELECT * FROM case_results WHERE case_id=?', (row['id'],)).fetchone()
                value = dict(result) if result else None
                if value:
                    actual = value.pop('actual_json')
                    value['actual'] = json.loads(actual) if actual else None
                case = StoredCase(row['id'], task_id, row['ordinal'], row['strategy'], json.loads(row['input_json']),
                                  json.loads(row['expectation_json']), row['source_sha256'], row['state'], value)
                case.to_case()  # Verify integrity before exposing or replaying persisted input.
                cases.append(case)
            return cases

    def save_case_result(self, task_id, result):
        if result.status not in {'PASSED', 'FAILED', 'ERROR', 'CANCELLED'}:
            raise ValueError('result must be terminal')
        started, finished = result.start_time, result.end_time
        if not all(math.isfinite(t) and t >= 0 for t in (started, finished)) or finished < started:
            raise ValueError('invalid result timestamps')
        actual = encode(asdict(result.observation)) if result.observation else None
        values = (result.status, actual, result.error_message, round((finished-started)*1000, 3),
                  result.attempt_count, started, finished)
        with self.database.connection(write=True) as db:
            task = self._required(db, task_id)
            case = db.execute('SELECT * FROM task_cases WHERE task_id=? AND logical_id=?', (task_id, result.case.id)).fetchone()
            expected = result.case.expectation or Expectation(kind='verdict', verdict=result.case.expected_status)
            if (case is None or case['input_json'] != encode(case_input(result.case))
                    or case['expectation_json'] != encode(asdict(expected))):
                raise ValueError('result input does not match saved task input')
            existing = db.execute('SELECT assertion_status,actual_json,reason,duration_ms,attempt_count,started_at,finished_at FROM case_results WHERE case_id=?', (case['id'],)).fetchone()
            if existing:
                if tuple(existing) != values:
                    raise ValueError('conflicting result already saved')
                return
            if task['state'] not in {'RUNNING', 'CANCEL_REQUESTED'}:
                raise ValueError('task is not executing')
            db.execute('INSERT INTO case_results VALUES (?,?,?,?,?,?,?,?)', (case['id'], *values))
            db.execute('UPDATE task_cases SET state=? WHERE id=?', (result.status, case['id']))

    def transition(self, task_id, allowed_from, target, error=None):
        if not allowed_from or any(target not in TRANSITIONS.get(state, set()) for state in allowed_from):
            raise ValueError('invalid task transition')
        with self.database.connection(write=True) as db:
            row = self._required(db, task_id)
            if row['state'] not in allowed_from:
                return False
            if target in TERMINAL and db.execute("SELECT 1 FROM task_cases WHERE task_id=? AND state IN ('PENDING','RUNNING') LIMIT 1", (task_id,)).fetchone():
                raise ValueError('task has unfinished cases')
            now = time.time()
            db.execute('UPDATE tasks SET state=?,started_at=?,finished_at=?,error_json=? WHERE id=? AND state=?',
                       (target, now if target == 'RUNNING' else row['started_at'], now if target in TERMINAL else None,
                        encode(error) if error else row['error_json'], task_id, row['state']))
            return True

    @staticmethod
    def _finish_cases(db, task_id, status, reason):
        now = time.time()
        rows = db.execute("SELECT id FROM task_cases WHERE task_id=? AND state IN ('PENDING','RUNNING')", (task_id,)).fetchall()
        for row in rows:
            db.execute('INSERT INTO case_results VALUES (?,?,?,?,?,?,?,?)', (row['id'], status, None, reason, 0, 0, now, now))
            db.execute('UPDATE task_cases SET state=? WHERE id=?', (status, row['id']))

    def finish_unstarted_cases(self, task_id, status, reason):
        if status not in {'ERROR', 'CANCELLED'}:
            raise ValueError('unfinished cases must be error or cancelled')
        with self.database.connection(write=True) as db:
            task = self._required(db, task_id)
            if task['state'] not in ACTIVE:
                raise ValueError('task is terminal')
            self._finish_cases(db, task_id, status, reason)

    def recover_interrupted(self):
        """Caller must hold the runtime OS lock; initialize alone never recovers tasks."""
        with self.database.connection(write=True) as db:
            rows = db.execute("SELECT id FROM tasks WHERE state IN ('PENDING','RUNNING','CANCEL_REQUESTED')").fetchall()
            for row in rows:
                self._finish_cases(db, row['id'], 'ERROR', 'PROCESS_INTERRUPTED')
                db.execute("UPDATE tasks SET state='INTERRUPTED',finished_at=?,error_json=? WHERE id=?",
                           (time.time(), encode({'stage': 'recovery', 'reason': 'PROCESS_INTERRUPTED'}), row['id']))
            return len(rows)

    def delete_task(self, task_id):
        with self.database.connection(write=True) as db:
            if self._required(db, task_id)['state'] in ACTIVE:
                raise ValueError('cannot delete active task')
            db.execute('DELETE FROM tasks WHERE id=?', (task_id,))

    def save_report(self, task_id, format, relative_path, sha256):
        path = PurePosixPath(relative_path)
        if (format not in {'html', 'json'} or not relative_path or path.is_absolute()
                or '..' in path.parts or ':' in relative_path or chr(92) in relative_path
                or not re.fullmatch(r'[0-9a-f]{64}', sha256)):
            raise ValueError('invalid report metadata')
        with self.database.connection(write=True) as db:
            self._required(db, task_id)
            existing = db.execute('SELECT * FROM reports WHERE task_id=? AND format=?', (task_id, format)).fetchone()
            if existing:
                if existing['relative_path'] != relative_path or existing['sha256'] != sha256:
                    raise ValueError('conflicting report already saved')
                return existing['id']
            report_id = str(uuid4())
            db.execute('INSERT INTO reports VALUES (?,?,?,?,?,?)',
                       (report_id, task_id, format, relative_path, sha256, time.time()))
            return report_id

    def get_report(self, task_id, format):
        if format not in {'html', 'json'}:
            raise ValueError('invalid report format')
        with self.database.connection() as db:
            self._required(db, task_id)
            row = db.execute('SELECT * FROM reports WHERE task_id=? AND format=?', (task_id, format)).fetchone()
            if row is None:
                raise KeyError((task_id, format))
            return dict(row)
