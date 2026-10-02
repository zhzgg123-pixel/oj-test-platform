"""Owned, journalled fixtures for the dedicated real OJ environment."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from config_center.profile_loader import ProfileLoader
from scripts.e2e_environment import authenticated_session, verify_environment

PROFILES = ('a_plus_b', 'max_of_two')
SCOPE_KEYS = ('base_url', 'compose_project', 'database', 'sut_sha', 'deployment_id')
FIELDS = ('title', 'description', 'input_desc', 'output_desc', 'difficulty',
          'sample_input', 'sample_output', 'time_limit_ms', 'memory_limit_kb')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


@contextmanager
def ledger_lock(path):
    """OS lock survives stale lock files and is released even on process death."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a+b', buffering=0) as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def save(path, ledger, *, create=False):
    content = json.dumps(ledger, ensure_ascii=False, indent=2) + '\n'
    if create:
        with path.open('x', encoding='utf-8') as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        return
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def new_ledger(environment):
    run_id = uuid.uuid4().hex
    entries = []
    for profile_id in PROFILES:
        profile = ProfileLoader().load(profile_id)
        definition = profile.definition
        sample, *rest = definition.fixtures
        payload = {'title': f'oj-e2e-{run_id}-{profile_id}',
                   'description': f'Isolated OJ test fixture; run_id={run_id}',
                   'input_desc': 'Two integers separated by whitespace',
                   'output_desc': definition.title, 'difficulty': 'easy',
                   'sample_input': sample.stdin, 'sample_output': sample.stdout,
                   'time_limit_ms': definition.time_limit_ms,
                   'memory_limit_kb': definition.memory_limit_kb,
                   'testcases': [{'input': f.stdin, 'output': f.stdout} for f in rest]}
        entries.append({'profile_id': profile_id, 'profile_sha256': profile.profile_sha256,
                        'payload': payload, 'payload_sha256': digest(payload),
                        'problem_id': None, 'state': 'planned'})
    return {'schema_version': 1, 'run_id': run_id,
            'scope': {key: environment[key] for key in SCOPE_KEYS}, 'problems': entries}


def valid_id(value):
    return type(value) is int and 0 < value <= 2147483647


def validate_ledger(ledger, environment):
    if (ledger.get('schema_version') != 1
            or not re.fullmatch('[0-9a-f]{32}', str(ledger.get('run_id', '')))
            or ledger.get('scope') != {key: environment[key] for key in SCOPE_KEYS}):
        raise ValueError('ledger belongs to a different or invalid deployment')
    entries = ledger.get('problems', [])
    if not isinstance(entries, list) or [p.get('profile_id') for p in entries] != list(PROFILES):
        raise ValueError('ledger must contain exactly the two distinct profiles')
    ids = []
    for entry in entries:
        payload = entry.get('payload', {})
        title = f"oj-e2e-{ledger['run_id']}-{entry['profile_id']}"
        if (payload.get('title') != title or digest(payload) != entry.get('payload_sha256')
                or not re.fullmatch('[0-9a-f]{64}', str(entry.get('profile_sha256', '')))
                or entry.get('state') not in {'planned', 'create_started', 'verified', 'delete_started', 'deleted'}):
            raise ValueError('ledger fixture content or identity is invalid')
        pid = entry.get('problem_id')
        if pid is not None:
            if not valid_id(pid) or pid in ids:
                raise ValueError('ledger problem IDs must be distinct positive integers')
            ids.append(pid)
        elif entry['state'] in {'verified', 'delete_started'}:
            raise ValueError('verified fixture requires a problem ID')
    return ledger


def body(response):
    data = response.json()
    if response.status_code != 200 or not isinstance(data, dict) or data.get('success') is not True:
        # Do not echo untrusted error bodies or credentials into logs.
        raise ValueError('real OJ fixture API did not succeed')
    return data


def detail(session, base_url, pid):
    response = session.get(f'{base_url}/api/problems/{pid}', timeout=10, allow_redirects=False)
    if response.status_code == 404 and response.json() == {'success': False, 'error': 'Problem not found'}:
        return None
    result = body(response).get('problem')
    if not isinstance(result, dict) or result.get('id') != pid:
        raise ValueError('problem readback identity differs')
    return result


def verify_content(problem, entry):
    if problem is None:
        raise ValueError('created problem content is missing')
    actual = {key: problem.get(key) for key in FIELDS}
    actual['testcases'] = [{'input': tc.get('input'), 'output': tc.get('output')}
                           for tc in problem.get('testcases', [])]
    if digest(actual) != entry['payload_sha256']:
        raise ValueError('problem content differs from owned fixture; refusing to modify it')


def exact_title_ids(session, base_url, title):
    result = body(session.get(base_url + '/api/problems', params={'search': title},
                              timeout=10, allow_redirects=False))
    problems = result.get('problems')
    if not isinstance(problems, list):
        raise ValueError('invalid problem listing')
    ids = [p['id'] for p in problems if p.get('title') == title]
    if len(ids) > 1 or any(not valid_id(pid) for pid in ids):
        raise ValueError('fixture title lookup is ambiguous')
    return ids


def seed(config_path, ledger_path):
    path = Path(ledger_path).resolve()
    with ledger_lock(path):
        if path.exists():
            raise FileExistsError('ledger already exists; inspect or clean it before starting a new run')
        environment = verify_environment(config_path)
        ledger = new_ledger(environment)
        save(path, ledger, create=True)
        base_url = ledger['scope']['base_url']
        with authenticated_session(base_url) as session:
            for entry in ledger['problems']:
                if exact_title_ids(session, base_url, entry['payload']['title']):
                    raise ValueError('new fixture title already exists')
                entry['state'] = 'create_started'
                save(path, ledger)  # Journal intent BEFORE the non-idempotent POST.
                response = session.post(base_url + '/api/admin/problems', json=entry['payload'],
                                        timeout=10, allow_redirects=False)
                pid = body(response).get('problem_id')
                if not valid_id(pid):
                    raise ValueError('create response has no valid ID; use cleanup for title reconciliation')
                entry['problem_id'] = pid
                save(path, ledger)
                verify_content(detail(session, base_url, pid), entry)
                entry['state'] = 'verified'
                save(path, ledger)
        return ledger


def cleanup(config_path, ledger_path):
    path = Path(ledger_path).resolve()
    with ledger_lock(path):
        environment = verify_environment(config_path)
        ledger = validate_ledger(json.loads(path.read_text(encoding='utf-8')), environment)
        base_url = ledger['scope']['base_url']
        with authenticated_session(base_url) as session:
            for entry in ledger['problems']:
                title = entry['payload']['title']
                ids = exact_title_ids(session, base_url, title)
                pid = entry['problem_id']
                if pid is None and not ids and entry['state'] == 'create_started':
                    raise ValueError('create outcome unresolved; preserve ledger and reconcile after server completion')
                if pid is None and ids:
                    if entry['state'] != 'create_started':
                        raise ValueError('unexpected remote fixture without recorded creation intent')
                    pid = ids[0]
                    verify_content(detail(session, base_url, pid), entry)
                    entry['problem_id'] = pid
                    save(path, ledger)
                if ids and ids != [pid]:
                    raise ValueError('title resolved to a different fixture ID')
                problem = detail(session, base_url, pid) if pid is not None else None
                if problem is not None:
                    if entry['state'] in {'planned', 'deleted'}:
                        raise ValueError('unexpected existing fixture state; refusing deletion')
                    verify_content(problem, entry)
                    entry['state'] = 'delete_started'
                    save(path, ledger)
                    body(session.post(f'{base_url}/api/admin/problems/{pid}/delete',
                                      timeout=10, allow_redirects=False))
                    if detail(session, base_url, pid) is not None:
                        raise ValueError('deleted fixture still exists')
                if exact_title_ids(session, base_url, title):
                    raise ValueError('fixture title still exists after cleanup')
                entry['state'] = 'deleted'
                save(path, ledger)
        return ledger
