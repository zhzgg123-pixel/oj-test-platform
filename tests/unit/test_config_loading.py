"""Use caller-selected files and consistent CLI > env > file > default precedence."""
import pytest

from config_center.config import AppConfig

pytestmark = pytest.mark.unit


def test_app_config_casts_environment_types(monkeypatch):
    monkeypatch.setenv('OJ_TIMEOUT', '2.5')
    config = AppConfig.load()
    assert config.oj.timeout == 2.5
    assert isinstance(config.oj.timeout, float)


def test_selected_file_is_used(tmp_path):
    path = tmp_path / 'specific.yaml'
    path.write_text('oj:\n  base_url: http://127.0.0.1:19001\n  timeout: 7\n', encoding='utf-8')
    config = AppConfig.load(config_path=path, environ={})
    assert config.oj.base_url == 'http://127.0.0.1:19001'
    assert config.oj.timeout == 7


def test_task_override_precedence(tmp_path):
    from config_center.config import load_task_config
    path = tmp_path / 'task.yaml'
    path.write_text('oj:\n  timeout: 7\ntest:\n  generate_case_count: 4\ntask:\n  seed: 11\n', encoding='utf-8')
    config = load_task_config(path, env={'OJ_TIMEOUT': '2.5', 'OJ_CASE_COUNT': '6', 'OJ_SEED': '12'},
                               overrides={'case_count': 8, 'seed': None})
    assert config.request_timeout == 2.5
    assert config.case_count == 8
    assert config.seed == 12


@pytest.mark.parametrize('contents', ['[]', 'typo: true', 'oj:\n  timeout: -1', 'task:\n  strategies: []'])
def test_invalid_file_fails_instead_of_using_defaults(tmp_path, contents):
    path = tmp_path / 'invalid.yaml'
    path.write_text(contents, encoding='utf-8')
    with pytest.raises(ValueError):
        AppConfig.load(config_path=path, environ={})


def test_requested_missing_file_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        AppConfig.load(config_path=tmp_path / 'absent.yaml', environ={})


def test_explicit_environment_name_matches_loaded_overlay():
    assert AppConfig.load(env='prod', environ={}).env == 'prod'


def test_environment_timeout_overrides_legacy_task_alias(tmp_path):
    from config_center.config import load_task_config
    path = tmp_path / 'legacy.yaml'
    path.write_text('task:\n  timeout: 8\n', encoding='utf-8')
    assert load_task_config(path, env={'OJ_TIMEOUT': '3'}).request_timeout == 3
