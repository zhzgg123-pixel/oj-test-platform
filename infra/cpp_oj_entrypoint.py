"""Translate private environment into the pinned SUT's config.json contract."""
import json
import os
from pathlib import Path


def runtime_config(environment):
    for key in ('E2E_DB_PASSWORD', 'E2E_ADMIN_PASSWORD'):
        if not environment.get(key):
            raise ValueError(f'{key} is required')
    return {'db': {'host':'mysql', 'port':3306, 'user':'oj_e2e_sut',
                   'password':environment['E2E_DB_PASSWORD'], 'database':'oj_platform_e2e'},
            'admin': {'username':'e2e_admin', 'password':environment['E2E_ADMIN_PASSWORD']},
            'judge': {'default_time_limit_ms':1000, 'default_memory_limit_kb':65536}}


def main():
    os.umask(0o077)
    target = Path('/runtime')
    config = runtime_config(os.environ)
    (target / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    for name in ('html', 'static'):
        link = target / name
        if not link.is_symlink():
            link.symlink_to(Path('/opt/oj') / name, target_is_directory=True)
    os.chdir(target)
    # Submitted programs inherit the server environment: do not give them bootstrap secrets.
    environment = {k:v for k,v in os.environ.items() if not k.startswith('E2E_')}
    os.execve('/opt/oj/cpp-oj', ['/opt/oj/cpp-oj'], environment)


if __name__ == '__main__':
    main()
