import pytest

from task_center.service import platform_revision


def test_container_revision_does_not_require_git(monkeypatch):
    revision = 'a' * 40
    monkeypatch.setenv('OJ_PLATFORM_SHA', revision)
    monkeypatch.setattr('task_center.service.subprocess.check_output',
                        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    assert platform_revision() == revision


@pytest.mark.parametrize('value', ['main', 'abc', 'a' * 40 + '\n', '<script>'])
def test_invalid_container_revision_is_rejected(monkeypatch, value):
    monkeypatch.setenv('OJ_PLATFORM_SHA', value)
    with pytest.raises(ValueError, match='OJ_PLATFORM_SHA'):
        platform_revision()
