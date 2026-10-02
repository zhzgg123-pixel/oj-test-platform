"""Copy text E2E evidence into a separate credential-redacted upload directory."""
import argparse
import json
from pathlib import Path
import subprocess


def collect(source, output, settings, docker_logs=False):
    source, output, settings = Path(source).resolve(), Path(output).resolve(), Path(settings)
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('evidence input and publication directories must be separate')
    if not settings.is_file():
        # Preparation can fail before credentials exist (for example SUT clone).
        # Publish only a fixed status, never unsanitized input or Docker output.
        output.mkdir(parents=True, exist_ok=False)
        (output/'collection.json').write_text(json.dumps({
            'status': 'NOT_RUN', 'files': [],
            'reason': 'Private settings unavailable; E2E evidence collection refused. See preparation job logs.',
        }, indent=2), encoding='utf-8')
        raise FileNotFoundError('private settings unavailable; only safe status was published')
    values = dict(line.split('=', 1) for line in settings.read_text(encoding='utf-8').splitlines() if line)
    secrets = [value for key, value in values.items() if 'PASSWORD' in key and value]
    if not secrets:
        raise ValueError('cannot sanitize evidence without the generated credentials')

    def sanitize(text):
        for secret in sorted(secrets, key=len, reverse=True):
            text = text.replace(secret, '[REDACTED]')
        return text

    output.mkdir(parents=True, exist_ok=False)
    copied = []
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix not in {'.json', '.html', '.xml', '.txt', '.log'}:
            continue
        if not path.resolve().is_relative_to(source):
            raise ValueError('evidence symlink escapes input directory')
        relative = path.relative_to(source)
        destination = output/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(sanitize(path.read_text(encoding='utf-8')), encoding='utf-8')
        copied.append(relative.as_posix())
    diagnostics = {}
    if docker_logs:
        for name, args in [('compose.log', ['logs', '--no-color']), ('services.json', ['ps', '--format', 'json'])]:
            result = subprocess.run(['docker', 'compose', '--env-file', str(settings),
                                     '-f', 'compose.e2e.yaml', *args],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            (output/name).write_text(sanitize(result.stdout + result.stderr), encoding='utf-8')
            diagnostics[name] = result.returncode
    (output/'collection.json').write_text(json.dumps({
        'files': copied, 'diagnostic_exit_codes': diagnostics,
        'scope': 'Redacted text evidence only; excludes databases and private settings',
    }, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('artifacts'))
    parser.add_argument('--output', type=Path, default=Path('ci-e2e-artifacts'))
    parser.add_argument('--settings', type=Path, default=Path('.env.e2e'))
    parser.add_argument('--docker-logs', action='store_true')
    args = parser.parse_args()
    collect(args.source, args.output, args.settings, args.docker_logs)


if __name__ == '__main__':
    main()
