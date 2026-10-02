"""Fail CI on absent/failed tests or missing, inconsistent demo report evidence."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import xml.etree.ElementTree as ET

from scripts.smoke_compose import require, validate_report


def check_evidence(junit_path, manifest_path, expected_sha):
    require(re.fullmatch(r'[0-9a-f]{40}', expected_sha), 'full expected SHA required')
    root = ET.parse(junit_path).getroot()
    require(root.tag in {'testsuites', 'testsuite'}, 'invalid JUnit root')
    cases = list(root.iter('testcase'))
    require(cases, 'no test cases executed')
    require(not list(root.iter('failure')) and not list(root.iter('error')), 'tests failed')
    for suite in root.iter():
        if suite.tag not in {'testsuites', 'testsuite'}:
            continue
        descendants = list(suite.iter('testcase'))
        expected = {'tests': len(descendants), 'failures': 0, 'errors': 0,
                    'skipped': sum(case.find('skipped') is not None for case in descendants)}
        for key, value in expected.items():
            if key in suite.attrib:
                require(int(suite.attrib[key]) == value, f'inconsistent JUnit {key}')
    executed = sum(case.find('skipped') is None for case in cases)
    require(executed > 0, 'all tests skipped')
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest['schema_version'] == 1 and manifest['scope'] == 'HTTP Mock only',
            'unsupported demo manifest')
    require(manifest['platform_sha'] == expected_sha, 'wrong manifest source SHA')
    contents, hashes = {}, {}
    for format in ('json', 'html'):
        entry = manifest['reports'][format]
        relative = PurePosixPath(entry['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and
                '\\' not in entry['path'] and ':' not in entry['path'], 'unsafe report path')
        path = (manifest_path.parent/relative).resolve()
        require(path.is_relative_to(manifest_path.parent.resolve()), 'report escapes artifact directory')
        body = path.read_bytes()
        require(body, 'empty report')
        digest = hashlib.sha256(body).hexdigest()
        require(digest == entry['sha256'], 'report digest mismatch')
        contents[format], hashes[format] = body, digest
    report = json.loads(contents['json'])
    validate_report(report, manifest['task_id'])
    require(report['task']['platform_sha'] == expected_sha, 'wrong report source SHA')
    require(report['summary']['total'] == report['summary']['passed'] == 6,
            'inconsistent demo summary')
    require(manifest['counts']['total'] == manifest['counts']['passed'] == 6,
            'inconsistent manifest counts')
    html = contents['html'].decode('utf-8')
    require('<html' in html.lower() and manifest['task_id'] in html and report['report_id'] in html,
            'HTML is missing report identity')
    return {'status': 'PASS', 'platform_sha': expected_sha, 'tests_executed': executed,
            'demo_total': len(report['all_cases']), 'report_sha256': hashes,
            'python': platform.python_version(), 'environment': platform.platform(),
            'scope': 'JUnit and HTTP Mock reports; not real C++ acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junit', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check_evidence(args.junit, args.demo, args.expected_sha)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(f'Evidence FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
