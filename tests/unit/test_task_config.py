"""Configuration must reject empty/ambiguous tasks before any OJ request."""
import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('overrides', [
    {'strategies': []}, {'strategies': ['unknown']}, {'case_count': 0}, {'case_count': 1001},
    {'strategies': ['random', 'random']}, {'case_count': 2},
    {'poll_interval': 2, 'poll_timeout': 1}, {'request_timeout': 0},
    {'mode': 'concurrent', 'max_workers': 17}, {'mode': 'other'},
    {'base_url': 'ftp://example.com'}, {'base_url': 'https://user:secret@example.com'},
    {'password': 'must-not-be-config'}, {'case_count': True}, {'problem_id': '../1'},
])
def test_invalid_config_is_rejected(overrides):
    from config_center.models import TaskConfig
    with pytest.raises(ValidationError):
        TaskConfig(**overrides)


def test_sequential_mode_uses_one_worker():
    from config_center.models import TaskConfig
    assert TaskConfig(mode='sequential', max_workers=8).max_workers == 1


def test_legacy_timeout_alias_is_normalized():
    from config_center.models import TaskConfig
    config = TaskConfig(timeout=2)
    assert config.request_timeout == 2
    assert config.model_dump()['request_timeout'] == 2
    assert 'timeout' not in config.model_dump()


def test_credentials_are_separate_and_not_serialized():
    from config_center.models import ExecutionCredentials
    credentials = ExecutionCredentials(username='tester', password='private-value')
    assert 'private-value' not in repr(credentials)
    assert 'password' not in credentials.model_dump()
    assert 'private-value' not in credentials.model_dump_json()
    assert credentials.password.get_secret_value() == 'private-value'
