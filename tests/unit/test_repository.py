from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3

import pytest

from config_center.models import TaskConfig
from config_center.profile_loader import ProfileLoader
from core_engine.case_engine.case_builder import CaseBuilder
from core_engine.contracts import Observation
from core_engine.executor.base_executor import CaseResult


@pytest.fixture
def inputs():
    config = TaskConfig(case_count=3)
    profile = ProfileLoader().load(config.profile_id)
    return config, profile, CaseBuilder().build(config, profile)


@pytest.fixture
def repo(tmp_path):
    from storage.repository import TaskRepository
    repository = TaskRepository(tmp_path / 'tasks.db')
    repository.initialize()
    return repository


def add(repo, inputs):
    return repo.insert_task(*inputs, platform_sha='test-sha', sut_sha=None)


def test_inputs_survive_reopen_with_exact_source(repo, inputs):
    from storage.repository import TaskRepository
    task_id = add(repo, inputs)
    reopened = TaskRepository(repo.db_path)
    reopened.initialize()
    task = reopened.get_task(task_id)
    assert task.id == task_id and task.state == 'PENDING'
    assert task.config == inputs[0].to_dict()
    assert task.profile == inputs[1].to_dict()
    saved = reopened.list_cases(task_id)
    assert [c.source_sha256 for c in saved] == [c.source_sha256 for c in inputs[2]]
    assert [c.to_case().code for c in saved] == [c.code for c in inputs[2]]
    assert len({c.id for c in saved}) == 3
    assert task.counts == dict(total=3, pending=3, running=0, passed=0, failed=0, error=0, cancelled=0)
    with sqlite3.connect(repo.db_path) as db:
        dump = '\n'.join(db.iterdump())
    assert 'password' not in dump.lower() and 'cookie' not in dump.lower()


def test_inputs_have_unique_physical_ids_across_tasks(repo, inputs):
    a, b = add(repo, inputs), add(repo, inputs)
    assert {c.id for c in repo.list_cases(a)}.isdisjoint(c.id for c in repo.list_cases(b))


def test_insert_rolls_back_all_inputs_on_database_failure(repo, inputs):
    with sqlite3.connect(repo.db_path) as db:
        db.execute("CREATE TRIGGER fail_second BEFORE INSERT ON task_cases WHEN NEW.ordinal=1 BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        add(repo, inputs)
    assert repo.list_tasks() == []
    with sqlite3.connect(repo.db_path) as db:
        assert db.execute('SELECT count(*) FROM task_cases').fetchone()[0] == 0


def test_rejects_mutated_source_and_mismatched_count_before_save(repo, inputs):
    config, profile, cases = inputs
    cases[0].code += '// changed'
    with pytest.raises(ValueError, match='hash'):
        add(repo, inputs)
    with pytest.raises(ValueError, match='count'):
        repo.insert_task(config, profile, cases[:1], 'sha', None)
    assert repo.list_tasks() == []


def test_result_is_idempotent_and_cannot_be_replaced(repo, inputs):
    task_id = add(repo, inputs)
    repo.transition(task_id, {'PENDING'}, 'RUNNING')
    result = CaseResult(case=inputs[2][0], status='PASSED', observation=Observation(kind='verdict', verdict='AC'), start_time=10, end_time=10.25)
    repo.save_case_result(task_id, result)
    repo.save_case_result(task_id, result)
    task = repo.get_task(task_id)
    assert task.counts['passed'] == 1 and task.counts['pending'] == 2
    saved = repo.list_cases(task_id)[0].result
    assert saved['duration_ms'] == 250 and saved['attempt_count'] == 1
    with pytest.raises(ValueError, match='conflict'):
        repo.save_case_result(task_id, replace(result, status='FAILED'))
    assert repo.list_cases(task_id)[0].result == saved


def test_foreign_result_cannot_overwrite_task_input(repo, inputs):
    task_id = add(repo, inputs)
    repo.transition(task_id, {'PENDING'}, 'RUNNING')
    changed = replace(inputs[2][0], code='different source')
    with pytest.raises(ValueError, match='input'):
        repo.save_case_result(task_id, CaseResult(case=changed, status='PASSED'))
    assert repo.get_task(task_id).counts['pending'] == 3


def test_transition_compare_and_set_preserves_cancellation(repo, inputs):
    task_id = add(repo, inputs)
    assert repo.transition(task_id, {'PENDING'}, 'RUNNING')
    assert not repo.transition(task_id, {'PENDING'}, 'RUNNING')
    assert repo.transition(task_id, {'RUNNING'}, 'CANCEL_REQUESTED')
    assert not repo.transition(task_id, {'RUNNING'}, 'COMPLETED')
    assert repo.get_task(task_id).state == 'CANCEL_REQUESTED'
    with pytest.raises(ValueError):
        repo.transition(task_id, {'CANCEL_REQUESTED'}, 'PENDING')


def test_cannot_complete_with_unfinished_cases(repo, inputs):
    task_id = add(repo, inputs)
    repo.transition(task_id, {'PENDING'}, 'RUNNING')
    with pytest.raises(ValueError, match='unfinished'):
        repo.transition(task_id, {'RUNNING'}, 'COMPLETED')


def test_recovery_preserves_finished_results_and_terminal_tasks(repo, inputs):
    active = add(repo, inputs)
    pending = add(repo, inputs)
    terminal = add(repo, inputs)
    repo.transition(active, {'PENDING'}, 'RUNNING')
    result = CaseResult(case=inputs[2][0], status='PASSED', start_time=1, end_time=2)
    repo.save_case_result(active, result)
    repo.finish_unstarted_cases(terminal, 'CANCELLED', 'CANCELLED')
    repo.transition(terminal, {'PENDING'}, 'CANCELLED')
    before = repo.get_task(terminal)
    assert repo.recover_interrupted() == 2
    assert repo.recover_interrupted() == 0
    assert repo.get_task(active).state == repo.get_task(pending).state == 'INTERRUPTED'
    assert repo.get_task(active).counts['passed'] == 1
    assert repo.get_task(active).counts['error'] == 2
    assert repo.list_cases(active)[1].result['reason'] == 'PROCESS_INTERRUPTED'
    assert repo.get_task(terminal) == before


def test_cross_thread_writes_use_separate_connections(repo, inputs):
    with ThreadPoolExecutor(max_workers=4) as pool:
        task_ids = list(pool.map(lambda _: add(repo, inputs), range(8)))
    assert len(set(task_ids)) == len(repo.list_tasks()) == 8


def test_database_settings_and_newer_schema_rejection(repo):
    from storage.database import Database
    with Database(repo.db_path).connection() as db:
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert db.execute('PRAGMA busy_timeout').fetchone()[0] >= 1000
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        db.execute('PRAGMA user_version=999')
    with pytest.raises(ValueError, match='version'):
        repo.initialize()


def test_pagination_delete_and_missing_task(repo, inputs):
    task_id = add(repo, inputs)
    with pytest.raises(ValueError):
        repo.list_tasks(limit=101)
    with pytest.raises(ValueError, match='active'):
        repo.delete_task(task_id)
    with pytest.raises(KeyError):
        repo.get_task('missing')
    repo.finish_unstarted_cases(task_id, 'CANCELLED', 'CANCELLED')
    repo.transition(task_id, {'PENDING'}, 'CANCELLED')
    repo.delete_task(task_id)
    assert repo.list_tasks() == []
    with sqlite3.connect(repo.db_path) as db:
        assert db.execute('SELECT count(*) FROM task_cases').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM case_results').fetchone()[0] == 0


def test_tampered_stored_source_fails_readback(repo, inputs):
    task_id = add(repo, inputs)
    with sqlite3.connect(repo.db_path) as db:
        row = db.execute('SELECT id,input_json FROM task_cases LIMIT 1').fetchone()
        changed = json.loads(row[1]); changed['code'] = 'tampered'
        db.execute('UPDATE task_cases SET input_json=? WHERE id=?', (json.dumps(changed), row[0]))
    with pytest.raises(ValueError, match='hash'):
        repo.list_cases(task_id)

def test_result_expectation_must_match_saved_input(repo, inputs):
    from core_engine.contracts import Expectation
    task_id = add(repo, inputs)
    repo.transition(task_id, {'PENDING'}, 'RUNNING')
    changed = replace(inputs[2][0], expectation=Expectation(kind='verdict', verdict='MLE'))
    with pytest.raises(ValueError, match='input'):
        repo.save_case_result(task_id, CaseResult(case=changed, status='PASSED'))


def test_report_metadata_is_task_bound_and_idempotent(repo, inputs):
    task_id = add(repo, inputs)
    digest = 'a' * 64
    report_id = repo.save_report(task_id, 'json', f'{task_id}/report.json', digest)
    assert repo.save_report(task_id, 'json', f'{task_id}/report.json', digest) == report_id
    assert repo.get_report(task_id, 'json')['sha256'] == digest
    with pytest.raises(ValueError, match='conflict'):
        repo.save_report(task_id, 'json', f'{task_id}/other.json', digest)
    for path in ('../escape.json', '/absolute.json', 'C:/outside.json', '..\\escape.json'):
        with pytest.raises(ValueError):
            repo.save_report(task_id, 'html', path, digest)
    with pytest.raises(KeyError):
        repo.get_report('missing', 'json')


def test_schema_migration_failure_is_atomic(tmp_path):
    from storage.repository import TaskRepository
    path = tmp_path / 'existing.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE task_cases (sentinel TEXT)')
        db.execute("INSERT INTO task_cases VALUES ('preserve')")
    with pytest.raises(sqlite3.OperationalError):
        TaskRepository(path).initialize()
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
        assert db.execute('SELECT sentinel FROM task_cases').fetchone()[0] == 'preserve'
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('task_cases',)]
