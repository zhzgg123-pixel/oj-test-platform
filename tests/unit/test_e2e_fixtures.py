"""Fixture ownership and uncertain-write recovery; live API proof is separate."""
from contextlib import contextmanager
from copy import deepcopy
import json

import pytest
import requests

from scripts import e2e_fixtures as fixtures


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return deepcopy(self.data)


class API:
    def __init__(self):
        self.problems = {}
        self.creates = self.deletes = 0
        self.timeout_after_create = False
        self.delay_create = False
        self.pending = None
        self.ignore_delete = False

    def get(self, url, **kwargs):
        if url.endswith('/api/problems'):
            return Reply({'success': True, 'problems': list(self.problems.values())})
        pid = int(url.rsplit('/', 1)[1])
        return (Reply({'success': True, 'problem': self.problems[pid]}) if pid in self.problems
                else Reply({'success': False, 'error': 'Problem not found'}, 404))

    def post(self, url, **kwargs):
        if url.endswith('/delete'):
            self.deletes += 1
            if not self.ignore_delete:
                self.problems.pop(int(url.split('/')[-2]))
            return Reply({'success': True})
        self.creates += 1
        pid = self.creates + 40
        self.problems[pid] = {**deepcopy(kwargs['json']), 'id': pid}
        for index, tc in enumerate(self.problems[pid]['testcases']):
            tc['id'] = pid * 10 + index
        if self.delay_create:
            self.pending = self.problems.pop(pid)
            raise requests.ReadTimeout('server has not committed yet')
        if self.timeout_after_create:
            raise requests.ReadTimeout('simulated lost response')
        return Reply({'success': True, 'problem_id': pid})


@pytest.fixture
def environment(monkeypatch):
    scope = {'base_url': 'http://127.0.0.1:18090', 'compose_project': 'oj-platform-e2e',
             'database': 'oj_platform_e2e', 'sut_sha': 'a' * 40, 'deployment_id': 'b' * 32}
    api = API()
    monkeypatch.setattr(fixtures, 'verify_environment', lambda path: deepcopy(scope))
    @contextmanager
    def session(url):
        assert url == scope['base_url']
        yield api
    monkeypatch.setattr(fixtures, 'authenticated_session', session)
    return api, scope


def test_seed_readback_and_cleanup_preserve_other_run(tmp_path, environment):
    api, _ = environment
    first, second = tmp_path/'first.json', tmp_path/'second.json'
    a = fixtures.seed('config', first)
    b = fixtures.seed('config', second)
    assert len(a['problems']) == len(b['problems']) == 2
    assert all(p['state'] == 'verified' and p['payload_sha256'] for p in a['problems'])
    assert a['run_id'] != b['run_id']
    fixtures.cleanup('config', first)
    assert set(api.problems) == {p['problem_id'] for p in b['problems']}
    fixtures.cleanup('config', first)
    assert api.deletes == 2
    fixtures.cleanup('config', second)
    assert not api.problems


def test_existing_ledger_never_repeats_create(tmp_path, environment):
    api, _ = environment
    path = tmp_path/'ledger.json'
    fixtures.seed('config', path)
    with pytest.raises(FileExistsError):
        fixtures.seed('config', path)
    assert api.creates == 2


def test_lost_create_response_is_recovered_by_exact_title_without_retry(tmp_path, environment):
    api, _ = environment
    api.timeout_after_create = True
    path = tmp_path/'ledger.json'
    with pytest.raises(requests.ReadTimeout):
        fixtures.seed('config', path)
    pending = json.loads(path.read_text())
    assert pending['problems'][0]['state'] == 'create_started'
    assert pending['problems'][0]['problem_id'] is None
    assert api.creates == 1
    fixtures.cleanup('config', path)
    assert api.creates == api.deletes == 1 and not api.problems


def test_inflight_create_cannot_be_marked_clean_before_late_commit(tmp_path, environment):
    api, _ = environment
    api.delay_create = True
    path = tmp_path/'ledger.json'
    with pytest.raises(requests.ReadTimeout):
        fixtures.seed('config', path)
    with pytest.raises(ValueError, match='unresolved'):
        fixtures.cleanup('config', path)
    assert json.loads(path.read_text())['problems'][0]['state'] == 'create_started'
    api.problems[api.pending['id']] = api.pending  # The original request commits later.
    fixtures.cleanup('config', path)
    assert api.creates == api.deletes == 1 and not api.problems


@pytest.mark.parametrize('mutation', ['deployment', 'hash', 'title', 'id', 'duplicate'])
def test_cleanup_rejects_invalid_ownership_before_delete(tmp_path, environment, mutation):
    api, scope = environment
    path = tmp_path/'ledger.json'
    ledger = fixtures.seed('config', path)
    if mutation == 'deployment':
        scope['deployment_id'] = 'c' * 32
    elif mutation == 'hash':
        ledger['problems'][0]['payload_sha256'] = '0' * 64
    elif mutation == 'title':
        ledger['problems'][0]['payload']['title'] = 'unrelated'
    elif mutation == 'id':
        ledger['problems'][0]['problem_id'] = True
    else:
        ledger['problems'][1] = deepcopy(ledger['problems'][0])
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError):
        fixtures.cleanup('config', path)
    assert api.deletes == 0


def test_changed_remote_data_is_not_deleted(tmp_path, environment):
    api, _ = environment
    path = tmp_path/'ledger.json'
    ledger = fixtures.seed('config', path)
    api.problems[ledger['problems'][0]['problem_id']]['testcases'][0]['output'] = 'edited'
    with pytest.raises(ValueError, match='content'):
        fixtures.cleanup('config', path)
    assert api.deletes == 0


def test_false_delete_success_requires_absence_readback(tmp_path, environment):
    api, _ = environment
    path = tmp_path/'ledger.json'
    fixtures.seed('config', path)
    api.ignore_delete = True
    with pytest.raises(ValueError, match='still exists'):
        fixtures.cleanup('config', path)
    ledger = json.loads(path.read_text())
    assert ledger['problems'][0]['state'] == 'delete_started'
