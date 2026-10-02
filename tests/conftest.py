"""Local-only test resources, always cleaned up even after failed assertions."""
from pathlib import Path
import os

import pytest
import requests

from tests.mock_oj.server import MockOJServer


@pytest.fixture(autouse=True)
def isolated_platform_environment(monkeypatch, request):
    """Local tests must never inherit deployment DB paths or credentials.

    Individual configuration tests may explicitly set their own environment.
    Real E2E keeps its opt-in environment and separate target validation.
    """
    if request.node.get_closest_marker('e2e'):
        return
    for name in list(os.environ):
        if name.startswith('OJ_'):
            monkeypatch.delenv(name, raising=False)


def pytest_addoption(parser):
    parser.addoption('--run-e2e', action='store_true', help='Enable real OJ tests explicitly')
    parser.addoption('--e2e-config', default=None, help='Isolated real OJ environment configuration')


def pytest_configure(config):
    if config.getoption('--run-e2e'):
        path = config.getoption('--e2e-config')
        if not path or not Path(path).is_file():
            raise pytest.UsageError('--run-e2e requires an existing --e2e-config file')


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if config.getoption('--run-e2e'):
        if not any(item.get_closest_marker('e2e') for item in items):
            raise pytest.UsageError('--run-e2e: no e2e tests selected')
        return
    selected, deselected = [], []
    for item in items:
        (deselected if item.get_closest_marker('e2e') else selected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


@pytest.fixture
def mock_oj_factory():
    servers = []
    def create(**kwargs):
        server = MockOJServer(**kwargs).start()
        servers.append(server)
        return server
    try:
        yield create
    finally:
        for server in reversed(servers):
            server.close()


@pytest.fixture
def mock_oj(mock_oj_factory):
    return mock_oj_factory()


@pytest.fixture
def http_session():
    with requests.Session() as session:
        session.trust_env = False
        yield session


@pytest.fixture
def logged_in_session(mock_oj, http_session):
    response = http_session.post(mock_oj.base_url + '/api/login',
                                 data={'username': 'tester', 'password': 'test-only'}, timeout=2)
    assert response.json()['success'] is True
    return http_session


@pytest.fixture
def database_path(tmp_path):
    return tmp_path / 'tasks.db'


@pytest.fixture
def report_dir(tmp_path):
    path = tmp_path / 'reports'
    path.mkdir()
    return path
