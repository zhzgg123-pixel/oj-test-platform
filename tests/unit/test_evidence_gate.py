import json
from pathlib import Path

import pytest

from scripts.check_evidence import check_evidence
from scripts.ci_demo import generate_demo


@pytest.fixture
def evidence(tmp_path):
    manifest = generate_demo(tmp_path/'demo', 'a'*40)
    junit = tmp_path/'junit.xml'
    junit.write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
                     '<testcase name="real_test"/></testsuite></testsuites>')
    return junit, manifest


def test_accepts_executed_tests_and_real_generated_report(evidence):
    junit, manifest = evidence
    result = check_evidence(junit, manifest, 'a'*40)
    assert result['status'] == 'PASS' and result['tests_executed'] == 1
    assert result['demo_total'] == 6


@pytest.mark.parametrize('xml', [
    '<testsuites><testsuite tests="0" failures="0" errors="0"/></testsuites>',
    '<testsuites><testsuite tests="1"><testcase name="skipped"><skipped/></testcase></testsuite></testsuites>',
    '<testsuites><testsuite tests="1" failures="0"><testcase name="bad"><failure/></testcase></testsuite></testsuites>',
    '<testsuites><testsuite tests="1" errors="1"><testcase name="bad"/></testsuite></testsuites>',
    '<testsuites><testsuite tests="2"><testcase name="one"/></testsuite></testsuites>',
])
def test_rejects_empty_skipped_failed_or_inconsistent_junit(evidence, xml):
    junit, manifest = evidence
    junit.write_text(xml)
    with pytest.raises(ValueError):
        check_evidence(junit, manifest, 'a'*40)


@pytest.mark.parametrize('mutation', ['missing_html', 'empty_html', 'changed_json', 'wrong_sha', 'escaped_path'])
def test_rejects_missing_changed_or_wrong_source_artifacts(evidence, mutation):
    junit, manifest = evidence
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if mutation == 'missing_html':
        (manifest.parent/'report.html').unlink()
    elif mutation == 'empty_html':
        (manifest.parent/'report.html').write_text('')
    elif mutation == 'changed_json':
        (manifest.parent/'report.json').write_text('{"summary":{"total":0}}')
    elif mutation == 'wrong_sha':
        data['platform_sha'] = 'b'*40
    else:
        data['reports']['html']['path'] = '../outside.html'
    manifest.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises((ValueError, FileNotFoundError)):
        check_evidence(junit, manifest, 'a'*40)
