"""Real-environment opt-in must never silently become an empty green run."""
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_explicit_e2e_without_configuration_fails():
    result = subprocess.run([sys.executable, '-m', 'pytest', '--run-e2e', '--collect-only', '-q'],
                            cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 4
    assert 'requires an existing --e2e-config' in result.stderr


def test_explicit_e2e_without_real_tests_fails(tmp_path):
    config = tmp_path / 'e2e.yaml'
    config.write_text('environment: isolated\n', encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'pytest', '--run-e2e',
                             '--e2e-config', str(config), '--collect-only', '-q',
                             'tests/integration/test_mock_harness.py'],
                            cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 4
    assert 'no e2e tests selected' in result.stderr
