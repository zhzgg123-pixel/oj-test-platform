"""Shared, non-mutating redaction for exported diagnostic data."""
import re

SENSITIVE_KEYS = {'password', 'passwd', 'token', 'accesstoken', 'refreshtoken',
                  'authorization', 'cookie', 'setcookie', 'sessionid', 'secret', 'apikey'}
EVIDENCE_FIELDS = {'result', 'passed', 'total', 'time_ms', 'memory_kb', 'compile_error', 'detail', 'success', 'error'}


def sensitive(key):
    return str(key).lower().replace('_', '').replace('-', '') in SENSITIVE_KEYS


def credential_values(value):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if sensitive(key) and isinstance(item, str) and item:
                found.append(item)
            found.extend(credential_values(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(credential_values(item))
    return found


def redact(value, secrets=()):
    secrets = sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True)
    pattern = re.compile('|'.join(re.escape(s) for s in secrets)) if secrets else None
    def clean(item):
        if isinstance(item, str):
            return pattern.sub('[REDACTED]', item) if pattern else item
        if isinstance(item, dict):
            return {key: '[REDACTED]' if sensitive(key) else clean(child)
                    for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(child) for child in item]
        return item
    return clean(value)


def safe_evidence(data, secrets=()):
    allowed = {key: value if value is None or type(value) in (str, int, float, bool) else '[INVALID_FIELD]'
               for key, value in data.items() if key in EVIDENCE_FIELDS}
    return redact(allowed, (*secrets, *credential_values(data)))
