import pytest

from scripts.prepare_e2e import render_schema
from infra.cpp_oj_entrypoint import runtime_config


def test_schema_removes_default_account_and_binds_scope():
    source = ('CREATE DATABASE IF NOT EXISTS cpp_oj DEFAULT CHARACTER SET utf8mb4;\n'
              'USE cpp_oj;\nCREATE TABLE users (id INT);\n'
              "INSERT INTO users (username, password, role) VALUES ('admin', MD5('admin123'), 'admin');\n")
    result = render_schema(source, 'a' * 40, 'b' * 32)
    assert 'CREATE DATABASE' not in result and 'USE cpp_oj' not in result
    assert 'admin123' not in result and 'INSERT INTO users' not in result
    assert 'CREATE TABLE users' in result and 'e2e_scope' in result
    assert 'a' * 40 in result and 'b' * 32 in result


def test_schema_rejects_unrecognized_source():
    with pytest.raises(ValueError):
        render_schema('DROP DATABASE production;', 'a' * 40, 'b' * 32)


def test_runtime_requires_credentials_and_uses_only_isolated_database():
    with pytest.raises(ValueError, match='E2E_DB_PASSWORD'):
        runtime_config({})
    cfg = runtime_config({'E2E_DB_PASSWORD': 'db-test', 'E2E_ADMIN_PASSWORD': 'admin-test',
                          'DB_HOST': 'production', 'DB_DATABASE': 'production'})
    assert cfg['db'] == {'host': 'mysql', 'port': 3306, 'user': 'oj_e2e_sut',
                         'password': 'db-test', 'database': 'oj_platform_e2e'}
    assert cfg['admin'] == {'username': 'e2e_admin', 'password': 'admin-test'}


def test_new_pin_uses_separate_checkout(tmp_path, monkeypatch):
    from pathlib import Path
    from scripts import prepare_e2e
    old = tmp_path/'.cache'/'cpp-oj'
    old.mkdir(parents=True)
    (old/'keep.txt').write_text('old source')
    cloned = []
    def fake_git(*args, cwd=None):
        if args[0] == 'clone':
            target = Path(args[-1])
            cloned.append(target)
            (target/'.git').mkdir(parents=True)
            (target/'schema.sql').write_text('CREATE DATABASE IF NOT EXISTS cpp_oj; USE cpp_oj; '
                "INSERT INTO users (username, password, role) VALUES ('admin', 'old', 'admin');")
        if args[:2] == ('remote', 'get-url'): return prepare_e2e.SUT_URL
        if args[0] == 'rev-parse': return prepare_e2e.SUT_SHA
        return ''
    monkeypatch.setattr(prepare_e2e, 'ROOT', tmp_path)
    monkeypatch.setattr(prepare_e2e, 'git', fake_git)
    prepare_e2e.prepare()
    assert cloned == [tmp_path/'.cache'/('cpp-oj-'+prepare_e2e.SUT_SHA)]
    assert (old/'keep.txt').read_text() == 'old source'
