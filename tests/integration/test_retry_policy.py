"""Retries must not submit a program twice after an ambiguous response."""
import pytest
import requests

from core_engine.api_client.request_client import RequestClient

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('statuses,expected_status,attempts', [
    ([503, 502, 200], 200, 3),
    ([504, 200], 200, 2),
    ([503, 503, 503, 200], 503, 3),
    ([500, 200], 500, 1),
    ([401, 200], 401, 1),
])
def test_get_retries_only_selected_transient_statuses(mock_oj_factory, statuses, expected_status, attempts):
    server = mock_oj_factory(get_statuses=statuses)
    client = RequestClient(server.base_url, timeout=1, retry_count=3, retry_delay=0)
    try:
        response = client.get('/')
        assert response.status_code == expected_status
        assert len(server.requests) == attempts
    finally:
        client._session.close()


def test_post_http_failure_is_returned_without_replay(mock_oj_factory):
    server = mock_oj_factory(submit_status=503)
    client = RequestClient(server.base_url, timeout=1, retry_count=3, retry_delay=0)
    try:
        client.post('/api/login', data={'username': 'tester', 'password': 'test-only'})
        response = client.post('/api/submit/1', data={'code': 'int main(){}'})
        assert response.status_code == 503
        assert len([r for r in server.requests if r['path'] == '/api/submit/1']) == 1
    finally:
        client._session.close()


@pytest.mark.parametrize('scenario,error', [('slow', requests.Timeout), ('disconnect', requests.ConnectionError)])
def test_post_transport_failure_does_not_replay(mock_oj_factory, scenario, error):
    server = mock_oj_factory(scenario=scenario, delay=0.3)
    client = RequestClient(server.base_url, timeout=0.05, retry_count=3, retry_delay=0)
    try:
        client.post('/api/login', data={'username': 'tester', 'password': 'test-only'})
        with pytest.raises(error):
            client.post('/api/submit/1', data={'code': 'int main(){}'})
        assert len([r for r in server.requests if r['path'] == '/api/submit/1']) == 1
    finally:
        client._session.close()


@pytest.mark.parametrize('status', [307, 308])
def test_post_redirect_does_not_replay_body(mock_oj_factory, status):
    server = mock_oj_factory(submit_status=status)
    client = RequestClient(server.base_url, timeout=1)
    try:
        client.post('/api/login', data={'username': 'tester', 'password': 'test-only'})
        response = client.post('/api/submit/1', data={'code': 'int main(){}'})
        assert response.status_code == status
        assert [r['path'] for r in server.requests if r['path'].startswith('/api/submit/')] == ['/api/submit/1']
    finally:
        client.close()
