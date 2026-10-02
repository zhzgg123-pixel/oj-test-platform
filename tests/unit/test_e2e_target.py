import pytest
from scripts.e2e_environment import validate_config, validate_scope, validate_network_membership
from scripts.prepare_e2e import SUT_SHA


def config():
    return {'schema_version': 1, 'base_url': 'http://127.0.0.1:18090',
            'compose_project': 'oj-platform-e2e', 'database': 'oj_platform_e2e',
            'sut_sha': SUT_SHA}


def test_network_boundary_keeps_sut_and_database_internal():
    valid = {'mysql': {'private'}, 'cpp-oj': {'private'}, 'gateway': {'private', 'ingress'}}
    assert validate_network_membership(valid) == ('private', 'ingress')
    for invalid in (
        {**valid, 'cpp-oj': {'private', 'ingress'}},
        {**valid, 'mysql': {'other'}},
        {**valid, 'gateway': {'ingress'}},
        {**valid, 'gateway': {'private', 'ingress', 'other'}},
    ):
        with pytest.raises(ValueError):
            validate_network_membership(invalid)


@pytest.mark.parametrize('key,value', [('base_url','https://production.example.com'),
    ('database','cpp_oj'), ('compose_project','existing-project'), ('sut_sha','a'*40),
    ('unexpected','ignored')])
def test_rejects_wrong_or_ambiguous_target(key, value):
    settings = config()
    settings[key] = value
    with pytest.raises(ValueError):
        validate_config(settings)


def test_scope_requires_exact_database_deployment_revision_and_admin():
    sha = config()['sut_sha']
    scope = f'oj_platform_e2e\n{"b"*32}\t{sha}\n1'
    validate_scope(scope, 'b'*32, sha)
    for incorrect in (scope.replace('oj_platform_e2e','cpp_oj'),
                      scope.replace('b'*32,'c'*32), scope.replace(sha,'d'*40),
                      scope[:-1] + '0', scope+'\nextra'):
        with pytest.raises(ValueError):
            validate_scope(incorrect, 'b'*32, sha)
