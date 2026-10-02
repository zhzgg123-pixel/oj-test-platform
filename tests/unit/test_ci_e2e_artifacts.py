from pathlib import Path

import pytest

from scripts.ci_e2e_artifacts import collect


def test_collects_only_text_evidence_and_redacts_credentials(tmp_path):
    source = tmp_path/'artifacts'
    source.mkdir()
    (source/'result.json').write_text('{"password":"private-password-value"}')
    (source/'junit.xml').write_text('<error>private-password-value</error>')
    (source/'tasks.db').write_bytes(b'private-password-value')
    settings = tmp_path/'.env.e2e'
    settings.write_text('E2E_ADMIN_PASSWORD=private-password-value\n')
    output = tmp_path/'publish'
    collect(source, output, settings)
    assert not (output/'tasks.db').exists()
    assert 'private-password-value' not in (output/'result.json').read_text()
    assert '[REDACTED]' in (output/'junit.xml').read_text()
    assert 'private-password-value' in (source/'result.json').read_text()


def test_rejects_output_inside_source(tmp_path):
    settings = tmp_path/'.env.e2e'
    settings.write_text('E2E_ADMIN_PASSWORD=secret\n')
    with pytest.raises(ValueError):
        collect(tmp_path, tmp_path/'publish', settings)


def test_missing_settings_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        collect(tmp_path/'artifacts', tmp_path/'publish', tmp_path/'missing')
