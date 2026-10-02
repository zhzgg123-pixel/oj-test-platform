"""Fail closed on container, database and pinned-source identity before E2E writes."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import yaml
from scripts.prepare_e2e import ROOT, SUT_SHA


def validate_config(config):
    expected = {'schema_version':1, 'base_url':'http://127.0.0.1:18090',
                'compose_project':'oj-platform-e2e', 'database':'oj_platform_e2e', 'sut_sha':SUT_SHA}
    if config != expected:
        raise ValueError('E2E configuration must identify the dedicated local Compose environment exactly')
    return config


def private_settings():
    return dict(line.split('=',1) for line in (ROOT / '.env.e2e').read_text(encoding='utf-8').splitlines() if line)


def docker(*arguments):
    result = subprocess.run(['docker', *arguments], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=30,
                            stdin=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError(f'Docker verification command failed with exit {result.returncode}')
    return result.stdout.strip()


def compose(*arguments):
    return docker('compose', '--env-file', '.env.e2e', '-f', 'compose.e2e.yaml', *arguments)


def validate_scope(output, deployment_id, sha):
    expected = ['oj_platform_e2e', f'{deployment_id}\t{sha}', '1']
    if output.splitlines() != expected:
        raise ValueError('database, deployment marker, source revision or bootstrap admin does not match')


def validate_network_membership(members):
    private = members['mysql']
    gateway = members['gateway']
    if (len(private) != 1 or members['cpp-oj'] != private
            or len(gateway) != 2 or not private < gateway):
        raise ValueError('SUT and database must share only the internal network; gateway must bridge ingress')
    return next(iter(private)), next(iter(gateway - private))


@contextmanager
def authenticated_session(base_url):
    settings = private_settings()
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(base_url + '/api/login', json={
            'username':'e2e_admin', 'password':settings['E2E_ADMIN_PASSWORD']},
            timeout=5, allow_redirects=False)
        if response.status_code != 200 or response.json().get('success') is not True:
            raise ValueError('isolated bootstrap login failed')
        if not session.cookies.get('session_id'):
            raise ValueError('isolated login did not establish a session')
        yield session


def verify_environment(config_path):
    config = validate_config(yaml.safe_load(Path(config_path).read_text(encoding='utf-8')))
    settings = private_settings()
    manifest = json.loads((ROOT / '.cache/e2e/manifest.json').read_text(encoding='utf-8'))
    if manifest['sut_sha'] != SUT_SHA or settings['E2E_SUT_SHA'] != SUT_SHA:
        raise ValueError('prepared source revision differs')
    if manifest['deployment_id'] != settings['E2E_DEPLOYMENT_ID']:
        raise ValueError('prepared deployment identity differs')
    instances = {}
    memberships = {}
    for service in ('mysql', 'cpp-oj', 'gateway'):
        container_id = compose('ps', '-q', service)
        if not container_id or '\n' in container_id:
            raise ValueError('expected exactly one container for each E2E service')
        data = json.loads(docker('inspect', container_id))[0]
        labels = data['Config']['Labels']
        if (labels.get('com.docker.compose.project'), labels.get('com.docker.compose.service')) != ('oj-platform-e2e',service):
            raise ValueError('container belongs to a different project or service')
        if not data['State']['Running'] or data['State'].get('Health',{}).get('Status') != 'healthy':
            raise ValueError('E2E container is not healthy')
        networks = data['NetworkSettings']['Networks']
        memberships[service] = {item['NetworkID'] for item in networks.values()}
        if service == 'cpp-oj':
            if labels.get('org.opencontainers.image.revision') != SUT_SHA:
                raise ValueError('SUT image revision differs from pinned source')
        if service == 'gateway':
            published = {port: bindings for port, bindings in data['NetworkSettings']['Ports'].items() if bindings}
            if published != {'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'18090'}]}:
                raise ValueError('gateway is not bound only to the expected loopback endpoint')
        elif any(data['NetworkSettings']['Ports'].values()):
            raise ValueError('isolated MySQL and SUT must not publish host ports directly')
        instances[service] = {'container_id':container_id, 'image_id':data['Image'], 'health':'healthy'}
    private_id, ingress_id = validate_network_membership(memberships)
    for network_id, internal, name in ((private_id, True, 'e2e'), (ingress_id, False, 'ingress')):
        network = json.loads(docker('network','inspect',network_id))[0]
        if (network['Internal'] != internal
                or network['Labels'].get('com.docker.compose.project') != 'oj-platform-e2e'
                or network['Labels'].get('com.docker.compose.network') != name):
            raise ValueError('network identity or isolation differs from the dedicated E2E topology')
    sql = "SELECT DATABASE(); SELECT deployment_id,sut_sha FROM e2e_scope; SELECT COUNT(*) FROM users WHERE username='e2e_admin' AND role='admin';"
    output = compose('exec','-T','mysql','sh','-c',
                     'MYSQL_PWD="$MYSQL_PASSWORD" mysql -h 127.0.0.1 -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -Nse "$1"',
                     'e2e-verify',sql)
    validate_scope(output,settings['E2E_DEPLOYMENT_ID'],SUT_SHA)
    with authenticated_session(config['base_url']) as session:
        response = session.get(config['base_url']+'/api/problems',timeout=5,allow_redirects=False)
        if response.status_code != 200 or response.json().get('success') is not True:
            raise ValueError('authenticated real OJ API failed')
    return {**config, 'deployment_id':settings['E2E_DEPLOYMENT_ID'], 'services':instances,
            'status':'PASS', 'scope':'infrastructure and authenticated API only; verdict matrix not yet run'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config_center/e2e.example.yaml')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    result = verify_environment(args.config)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True,exist_ok=True)
        args.evidence.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
