"""Prepare only the pinned, isolated C++ checkout and private local E2E settings."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SUT_SHA = 'fa5ffe317f136f29039bc66e734fc687c4531e10'
SUT_URL = 'https://gitee.com/chasing-dreams-zhuo/cpp-oj.git'


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True,
                                   stdin=subprocess.DEVNULL).strip()


def render_schema(source, sha, deployment_id):
    if not re.fullmatch('[0-9a-f]{40}', sha) or not re.fullmatch('[0-9a-f]{32}', deployment_id):
        raise ValueError('invalid source or deployment identity')
    schema, databases = re.subn(r'CREATE DATABASE IF NOT EXISTS cpp_oj[^;]*;', '', source)
    schema, uses = re.subn(r'USE cpp_oj\s*;', '', schema)
    schema, admins = re.subn(r'INSERT INTO users\s*\(username, password, role\)[^;]*;', '', schema)
    if (databases, uses, admins) != (1, 1, 1) or 'admin123' in schema:
        raise ValueError('unrecognized upstream initialization schema')
    return (schema + '\nCREATE TABLE e2e_scope (deployment_id CHAR(32) PRIMARY KEY, '
            'sut_sha CHAR(40) NOT NULL);\n'
            f"INSERT INTO e2e_scope VALUES ('{deployment_id}', '{sha}');\n")


def prepare():
    source = ROOT / '.cache' / ('cpp-oj-' + SUT_SHA)
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        git('clone', '--no-checkout', SUT_URL, str(source))
        git('checkout', '--detach', SUT_SHA, cwd=source)
    if not (source / '.git').exists():
        raise ValueError('existing SUT path is not the expected checkout')
    if git('remote', 'get-url', 'origin', cwd=source) != SUT_URL:
        raise ValueError('existing SUT remote differs; refusing to change it')
    if git('rev-parse', 'HEAD', cwd=source) != SUT_SHA:
        raise ValueError('existing SUT version differs; refusing to overwrite it')
    if git('status', '--porcelain', '--untracked-files=all', cwd=source):
        raise ValueError('SUT has local changes; refusing to overwrite or build them')
    settings = ROOT / '.env.e2e'
    if not settings.exists():
        values = {'E2E_SUT_SHA': SUT_SHA, 'E2E_DEPLOYMENT_ID': secrets.token_hex(16),
                  'E2E_DB_PASSWORD': secrets.token_hex(24),
                  'E2E_ROOT_PASSWORD': secrets.token_hex(24),
                  'E2E_ADMIN_PASSWORD': secrets.token_hex(24)}
        fd = os.open(settings, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    else:
        values = dict(line.split('=', 1) for line in settings.read_text(encoding='utf-8').splitlines() if line)
        expected = {'E2E_SUT_SHA':40, 'E2E_DEPLOYMENT_ID':32, 'E2E_DB_PASSWORD':48,
                    'E2E_ROOT_PASSWORD':48, 'E2E_ADMIN_PASSWORD':48}
        if set(values) != set(expected) or any(not re.fullmatch('[0-9a-f]{%d}' % size, values[key])
                                              for key,size in expected.items()):
            raise ValueError('existing E2E settings have unexpected fields or values')
        if values['E2E_SUT_SHA'] != SUT_SHA:
            raise ValueError('existing E2E settings belong to another source version')
    schema_source = (source / 'schema.sql').read_text(encoding='utf-8-sig')
    schema = render_schema(schema_source, SUT_SHA, values['E2E_DEPLOYMENT_ID'])
    output = ROOT / '.cache' / 'e2e'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'init.sql').write_text(schema, encoding='utf-8', newline='\n')
    manifest = {'sut_sha':SUT_SHA, 'deployment_id':values['E2E_DEPLOYMENT_ID'],
                'source_schema_sha256':hashlib.sha256(schema_source.encode()).hexdigest(),
                'derived_schema_sha256':hashlib.sha256(schema.encode()).hexdigest(),
                'database':'oj_platform_e2e', 'compose_project':'oj-platform-e2e'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(f'Prepared pinned C++ OJ {SUT_SHA}; private credentials retained locally; no database contacted.')


if __name__ == '__main__':
    prepare()
