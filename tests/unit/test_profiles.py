"""A profile is validated input plus an immutable replay snapshot of its source."""
import hashlib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def write_profile(root, *, profile_id='sample', path='templates/ac.cpp'):
    (root / 'templates').mkdir(exist_ok=True)
    (root / 'templates/ac.cpp').write_text('int main() { return 0; }\n', encoding='utf-8')
    document = {'schema_version': 1, 'id': profile_id, 'title': 'Sample', 'language': 'cpp',
        'fixtures': [{'stdin': '1 2\n', 'stdout': '3\n'}],
        'strategies': {
            'random': {'templates': [{'path': path, 'expected_verdict': 'AC'}]},
            'boundary': {'templates': [{'path': path, 'expected_verdict': 'AC'}]},
            'rule': {'scenarios': [{'name': 'anonymous', 'path': path, 'auth_mode': 'anonymous',
                                   'expectation': {'kind': 'http_error', 'http_status': 401}}]}}}
    (root / f'{profile_id}.yaml').write_text(yaml.safe_dump(document), encoding='utf-8')
    return document


@pytest.mark.parametrize('profile_id', ['a_plus_b', 'max_of_two'])
def test_bundled_profiles_have_complete_replay_snapshot(profile_id):
    from config_center.profile_loader import ProfileLoader
    profile = ProfileLoader(ROOT / 'profiles').load(profile_id)
    snapshot = profile.to_dict()
    assert snapshot['definition']['id'] == profile_id
    assert len(snapshot['definition']['fixtures']) >= 2
    assert len(profile.profile_sha256) == 64
    assert snapshot['template_sources']
    for path, source in snapshot['template_sources'].items():
        assert profile.source_hashes[path] == hashlib.sha256(source.encode('utf-8')).hexdigest()


def test_template_edit_changes_new_snapshot_but_not_old_snapshot(tmp_path):
    from config_center.profile_loader import ProfileLoader
    write_profile(tmp_path)
    loader = ProfileLoader(tmp_path)
    original = loader.load('sample')
    original_snapshot = original.to_dict()
    (tmp_path / 'templates/ac.cpp').write_text('int main() { return 1; }\n', encoding='utf-8')
    modified = loader.load('sample')
    assert original.profile_sha256 != modified.profile_sha256
    assert original.to_dict() == original_snapshot


@pytest.mark.parametrize('path', ['../outside.cpp', '/absolute.cpp', 'templates/missing.cpp'])
def test_bad_template_path_is_rejected(tmp_path, path):
    from config_center.profile_loader import ProfileLoader
    write_profile(tmp_path, path=path)
    with pytest.raises(ValueError):
        ProfileLoader(tmp_path).load('sample')


@pytest.mark.parametrize('profile_id', ['../sample', '/sample', 'missing', 'sample.yaml'])
def test_invalid_or_missing_profile_fails_explicitly(tmp_path, profile_id):
    from config_center.profile_loader import ProfileLoader
    write_profile(tmp_path)
    with pytest.raises(ValueError):
        ProfileLoader(tmp_path).load(profile_id)


@pytest.mark.parametrize('mutation', ['empty', 'unknown', 'bad_expectation', 'id_mismatch', 'no_fixture'])
def test_invalid_schema_is_rejected(tmp_path, mutation):
    from config_center.profile_loader import ProfileLoader
    document = write_profile(tmp_path)
    if mutation == 'empty':
        document['strategies']['random']['templates'] = []
    elif mutation == 'unknown':
        document['strategies']['typo'] = {}
    elif mutation == 'bad_expectation':
        document['strategies']['rule']['scenarios'][0]['expectation'] = {'kind': 'verdict', 'verdict': 'ERROR'}
    elif mutation == 'id_mismatch':
        document['id'] = 'different'
    else:
        document['fixtures'] = []
    (tmp_path / 'sample.yaml').write_text(yaml.safe_dump(document), encoding='utf-8')
    with pytest.raises(ValueError):
        ProfileLoader(tmp_path).load('sample')


def test_two_problem_profiles_do_not_share_same_correct_solution():
    from config_center.profile_loader import ProfileLoader
    loader = ProfileLoader(ROOT / 'profiles')
    plus = loader.load('a_plus_b')
    maximum = loader.load('max_of_two')
    plus_source = plus.template_sources['templates/a_plus_b/ac.cpp']
    max_source = maximum.template_sources['templates/max_of_two/ac.cpp']
    assert 'a + b' in plus_source
    assert 'std::max(a, b)' in max_source
    assert plus_source != max_source
