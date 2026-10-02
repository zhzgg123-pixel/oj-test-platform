"""Real compiler/judge results through TaskService; never substitutes verdicts."""
import pytest
import time
import json
from config_center.models import ExecutionCredentials
from scripts.e2e_environment import authenticated_session
from scripts.e2e_fixtures import detail

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize('profile_id', ['a_plus_b', 'max_of_two'])
@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
@pytest.mark.parametrize('verdict', ['AC', 'WA', 'CE', 'TLE', 'RE'])
def test_real_verdict(real_oj_runner, profile_id, mode, verdict):
    task, cases = real_oj_runner.run_verdict(profile_id, mode, verdict)
    assert task.state == 'COMPLETED'
    assert len(cases) == task.counts['total'] == task.counts['passed'] == 1
    assert cases[0].state == 'PASSED'
    assert cases[0].result['actual']['verdict'] == verdict
    assert cases[0].result['actual']['http_status'] == 200
    assert cases[0].result['actual']['evidence']['result'] == verdict


@pytest.mark.parametrize('profile_id', ['a_plus_b', 'max_of_two'])
@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
def test_real_batch_results_and_http_overlap(real_oj_runner, profile_id, mode):
    runner = real_oj_runner
    config = runner.select_seed(runner.config(profile_id, mode, case_count=5),
        lambda cases: {c.expectation.verdict for c in cases} == {'AC', 'WA', 'CE', 'TLE', 'RE'})
    task, cases = runner.finish(runner.start(config))
    assert task.state == 'COMPLETED' and task.counts['passed'] == 5
    assert len(runner.requests) == len(cases) == 5
    for case in cases:
        assert case.result['actual']['verdict'] == case.expectation['verdict']
        assert case.result['attempt_count'] == 1
        assert sum(r['source_sha256'] == case.source_sha256 for r in runner.requests) == 1
    events = [(r['started'], 1) for r in runner.requests] + [(r['finished'], -1) for r in runner.requests]
    active = peak = 0
    for _, delta in sorted(events):
        active += delta
        peak = max(peak, active)
    assert active == 0
    if mode == 'concurrent':
        assert 2 <= peak <= config.max_workers
        assert len({r['adapter_id'] for r in runner.requests}) == 5
        assert len({r['session_sha256'] for r in runner.logins if r['success']}) == 5
    else:
        assert peak == 1


@pytest.mark.parametrize('profile_id', ['a_plus_b', 'max_of_two'])
@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
def test_real_anonymous_missing_problem_and_empty_code(real_oj_runner, profile_id, mode):
    runner = real_oj_runner
    with authenticated_session(runner.scope['base_url']) as session:
        assert detail(session, runner.scope['base_url'], 2147483647) is None
    task, cases = runner.finish(runner.start(runner.config(profile_id, mode,
                                                          strategies=['rule'], case_count=3)))
    assert task.state == 'COMPLETED' and task.counts['passed'] == 3
    assert cases[0].result['actual']['http_status'] == 401
    assert cases[1].result['actual']['error_code'] == 'PROBLEM_NOT_FOUND'
    assert cases[2].result['actual']['error_code'] == 'CODE_REQUIRED'
    assert len(runner.requests) == 3


@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
def test_real_failed_login_does_not_submit(real_oj_runner, mode):
    runner = real_oj_runner
    task, cases = runner.finish(runner.start(runner.config('a_plus_b', mode),
        ExecutionCredentials(username='e2e_admin', password='deliberately-invalid-e2e-password')))
    assert task.state == 'FAILED' and task.error['reason'] == 'LOGIN_FAILED'
    assert task.counts['error'] == len(cases) == 1
    assert not runner.requests
    assert runner.logins and all(not event['success'] for event in runner.logins)


@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
def test_real_cancel_retains_inflight_results_and_stops_refill(real_oj_runner, mode):
    runner = real_oj_runner
    config = runner.config('a_plus_b', mode, case_count=18)
    config = runner.select_seed(config,
        lambda cases: all(c.expectation.verdict == 'TLE' for c in cases[:config.max_workers]))
    task_id = runner.start(config)
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        with runner.lock:
            initial = list(runner.requests)
            if len(initial) == config.max_workers and all(r['finished'] is None for r in initial):
                admitted = {(r['adapter_id'], r['started']) for r in initial}
                break
        time.sleep(0.01)
    else:
        pytest.fail('did not observe the complete initial batch of real submissions in flight')
    runner.service.cancel(task_id)
    task, cases = runner.finish(task_id)
    (runner.root/'cancel-boundary.json').write_text(json.dumps({
        'task_id': task_id, 'mode': mode, 'before_cancel': sorted(admitted),
        'after_complete': [(r['adapter_id'], r['started']) for r in runner.requests]
    }, indent=2)+'\n', encoding='utf-8')
    assert task.state == 'CANCELLED'
    sent = len(runner.requests)
    assert {(r['adapter_id'], r['started']) for r in runner.requests} == admitted
    assert sent == config.max_workers
    assert task.counts['passed'] == sent
    assert task.counts['cancelled'] == 18-sent
    assert task.error['remote_execution_may_continue'] is True
    assert sum(c.result['attempt_count'] for c in cases) == sent
    assert all(c.result['actual']['verdict'] == 'TLE' for c in cases if c.state == 'PASSED')
