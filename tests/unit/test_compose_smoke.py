from copy import deepcopy
import pytest
from scripts.smoke_compose import validate_report


def report():
    ac = {'status': 'PASSED', 'expectation': {'kind': 'verdict', 'verdict': 'AC'},
          'observation': {'kind': 'verdict', 'verdict': 'AC'}}
    reject = {'status': 'PASSED', 'expectation': {'kind': 'http_error', 'http_status': 401},
              'observation': {'kind': 'http_error', 'http_status': 401}}
    return {'task': {'id': 'demo', 'platform_sha': 'a' * 40},
            'all_cases': [deepcopy(ac) for _ in range(5)] + [reject]}


def test_accepts_nonempty_ac_and_rejection_report():
    validate_report(report(), 'demo')


@pytest.mark.parametrize('mutation', ['empty', 'wrong_task', 'failed', 'no_ac', 'no_rejection'])
def test_rejects_incomplete_or_failed_demo(mutation):
    data = report()
    if mutation == 'empty':
        data['all_cases'] = []
    elif mutation == 'wrong_task':
        data['task']['id'] = 'another'
    elif mutation == 'failed':
        data['all_cases'][0]['status'] = 'FAILED'
    elif mutation == 'no_ac':
        for case in data['all_cases'][:-1]:
            case['observation']['verdict'] = 'WA'
    else:
        data['all_cases'][-1]['observation']['http_status'] = 200
    with pytest.raises(ValueError):
        validate_report(data, 'demo')


@pytest.mark.parametrize('mutation', ['expected_wa', 'expected_403', 'wrong_kind', 'unknown_sha'])
def test_rejects_false_pass_and_missing_version(mutation):
    data = report()
    if mutation == 'expected_wa':
        for case in data['all_cases'][:-1]:
            case['expectation']['verdict'] = 'WA'
    elif mutation == 'expected_403':
        data['all_cases'][-1]['expectation']['http_status'] = 403
    elif mutation == 'wrong_kind':
        data['all_cases'][-1]['observation']['kind'] = 'transport_error'
    else:
        data['task']['platform_sha'] = 'unknown'
    with pytest.raises(ValueError):
        validate_report(data, 'demo')
