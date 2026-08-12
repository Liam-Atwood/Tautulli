import logging

import pytest
import requests

from plexpy.media_backend.errors import (
    BackendAuthError, BackendConfigurationError, BackendConnectionError,
    BackendFeatureUnsupportedError, BackendNotFoundError, BackendRateLimitError,
    BackendServerError,
)
from plexpy.media_backend.jellyfin import (
    JellyfinApi10_10, JellyfinApi10_11, JellyfinClient, JellyfinImage,
    build_authorization_header, select_api_profile,
)
from plexpy.media_backend.jellyfin.client import normalize_base_url


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b'', headers=None, json_error=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


class FakeSession:
    def __init__(self, responses=()):
        self.headers = {}
        self.responses = list(responses)
        self.requests = []
        self.mounts = {}
        self.closed = False

    def mount(self, prefix, adapter):
        self.mounts[prefix] = adapter

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


@pytest.mark.parametrize(('raw', 'expected'), [
    ('HTTPS://Example.COM:8920/', 'https://example.com:8920'),
    ('http://example.com/jellyfin///', 'http://example.com/jellyfin'),
    ('http://[2001:db8::1]:8096/base/', 'http://[2001:db8::1]:8096/base'),
])
def test_normalize_base_url_preserves_proxy_path(raw, expected):
    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize('raw', [
    '', 'example.com', 'ftp://example.com', 'http://user:pass@example.com',
    'http://example.com?api_key=secret', 'http://example.com/#fragment',
    'http://example.com:invalid', 'http://example.com/\r\nX-Evil: yes',
])
def test_normalize_base_url_rejects_unsafe_values(raw):
    with pytest.raises(BackendConfigurationError):
        normalize_base_url(raw)


def test_authorization_matches_official_mediabrowser_shape_and_rejects_injection():
    header = build_authorization_header(
        'secret-token', client='Tautulli', device='Test Host',
        device_id='stable-device', version='1.2.3')
    assert header == (
        'MediaBrowser Client="Tautulli", Device="Test Host", DeviceId="stable-device", '
        'Version="1.2.3", Token="secret-token"')
    with pytest.raises(BackendConfigurationError):
        build_authorization_header('secret\r\nX-Evil: yes')
    with pytest.raises(BackendConfigurationError):
        build_authorization_header('')


def test_client_reuses_session_sets_transport_and_does_not_close_injected_session():
    session = FakeSession([FakeResponse(payload={'Id': 'server', 'Version': '10.11.11'})])
    client = JellyfinClient(
        'https://example.invalid/jellyfin/', 'secret-token', session=session,
        verify_ssl=False, timeout=(3, 9), device_id='test-device')
    info = client.connect()
    assert info['Id'] == 'server'
    assert client.server_id == 'server'
    assert client.server_version == '10.11.11'
    assert isinstance(client.api_profile, JellyfinApi10_11)
    assert set(session.mounts) == {'http://', 'https://'}
    assert 'secret-token' in session.headers['Authorization']
    method, url, kwargs = session.requests[0]
    assert (method, url) == ('GET', 'https://example.invalid/jellyfin/System/Info')
    assert kwargs['timeout'] == (3.0, 9.0) and kwargs['verify'] is False
    client.close()
    assert not session.closed


def test_client_context_manager_closes_owned_session(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(requests, 'Session', lambda: session)
    with JellyfinClient('http://example.invalid', 'token') as client:
        assert client.session is session
    assert session.closed


def test_endpoint_methods_encode_paths_and_parameters():
    responses = [
        FakeResponse(payload=[]), FakeResponse(payload={'Id': 'item'}),
        FakeResponse(payload={'Items': []}), FakeResponse(payload=[]),
        FakeResponse(payload=[]), FakeResponse(
            content=b'image', headers={'Content-Type': 'image/png', 'ETag': 'tag-1'}),
    ]
    session = FakeSession(responses)
    client = JellyfinClient('http://example.invalid/base', 'token', session=session)
    assert client.get_sessions(active=True) == []
    assert client.get_item('id/with slash', user_id='user', fields=['Path', 'MediaSources']) == {'Id': 'item'}
    assert client.get_items(includeItemTypes=['Movie', 'Episode'], limit=5, ignored=None) == {'Items': []}
    assert client.get_users() == []
    assert client.get_libraries() == []
    image = client.get_image('item', maxWidth=300)
    assert image == JellyfinImage(b'image', 'image/png', 'tag-1')
    assert session.requests[1][1].endswith('/Items/id%2Fwith%20slash')
    assert session.requests[1][2]['params'] == {'userId': 'user', 'fields': 'Path,MediaSources'}
    assert session.requests[2][2]['params'] == {'includeItemTypes': 'Movie,Episode', 'limit': 5}
    assert session.requests[5][1].endswith('/Items/item/Images/Primary/0')


def test_no_content_and_malformed_json():
    session = FakeSession([
        FakeResponse(status=204),
        FakeResponse(status=200, json_error=ValueError('contains-secret-body')),
    ])
    client = JellyfinClient('http://example.invalid', 'token', session=session)
    assert client._request('POST', 'fixture') is None
    with pytest.raises(BackendServerError, match='malformed JSON') as error:
        client.get_users()
    assert 'contains-secret-body' not in str(error.value)


@pytest.mark.parametrize(('version', 'profile'), [
    ('10.10.7', JellyfinApi10_10), ('10.10.99', JellyfinApi10_10),
    ('10.11.0', JellyfinApi10_11), ('10.11.11-unstable', JellyfinApi10_11),
])
def test_version_profile_selection(version, profile):
    selected = select_api_profile(version)
    assert isinstance(selected, profile)


@pytest.mark.parametrize('version', ['10.10.6', '9.9.9', '12.0.0', 'invalid', None])
def test_version_profile_rejects_unsupported_or_invalid_versions(version):
    error = BackendServerError if version in ('invalid', None) else BackendFeatureUnsupportedError
    with pytest.raises(error):
        select_api_profile(version)


def test_connect_requires_complete_system_information():
    client = JellyfinClient(
        'http://example.invalid', 'token', session=FakeSession([FakeResponse(payload={'Version': '10.11.11'})]))
    with pytest.raises(BackendServerError, match='incomplete'):
        client.connect()
    assert client.server_id is None and client.api_profile is None


@pytest.mark.parametrize(('status', 'error'), [
    (400, BackendServerError), (401, BackendAuthError), (403, BackendAuthError),
    (404, BackendNotFoundError), (409, BackendServerError),
    (429, BackendRateLimitError), (500, BackendServerError), (503, BackendServerError),
])
def test_http_error_mapping(status, error):
    response = FakeResponse(status=status, headers={'Retry-After': '12'})
    client = JellyfinClient('http://example.invalid', 'token', session=FakeSession([response]))
    with pytest.raises(error) as raised:
        client.get_users()
    assert raised.value.status_code == status
    if status == 429:
        assert raised.value.retry_after == '12'


@pytest.mark.parametrize('request_error', [
    requests.exceptions.Timeout('token=raw-secret'),
    requests.exceptions.SSLError('token=raw-secret'),
    requests.exceptions.ConnectionError('token=raw-secret'),
    requests.exceptions.RequestException('token=raw-secret'),
])
def test_connection_errors_do_not_leak_exception_details(request_error):
    client = JellyfinClient(
        'http://example.invalid', 'token', session=FakeSession([request_error]))
    with pytest.raises(BackendConnectionError) as raised:
        client.get_users()
    assert 'raw-secret' not in str(raised.value)


def test_retry_policy_is_safe_and_limited_to_three_attempts():
    session = FakeSession()
    JellyfinClient('http://example.invalid', 'token', session=session)
    retry = session.mounts['http://'].max_retries
    assert retry.total == 2
    assert retry.allowed_methods == frozenset({'GET', 'HEAD'})
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.respect_retry_after_header


def test_trace_contains_no_token(caplog):
    session = FakeSession([FakeResponse(payload=[])])
    client = JellyfinClient(
        'http://example.invalid', 'top-secret-token', trace=True, session=session)
    with caplog.at_level(logging.DEBUG):
        client.get_users()
    assert 'top-secret-token' not in caplog.text
    assert 'GET http://example.invalid/Users completed status=200' in caplog.text


def test_trace_records_status_without_token(caplog):
    session = FakeSession([FakeResponse(status=403)])
    client = JellyfinClient(
        'http://example.invalid', 'top-secret-token', trace=True, session=session)
    with caplog.at_level(logging.DEBUG), pytest.raises(BackendAuthError):
        client.get_users()
    assert 'status=403' in caplog.text
    assert 'top-secret-token' not in caplog.text


def test_factory_still_rejects_jellyfin_runtime_selection():
    from plexpy.media_backend.factory import get_media_backend
    with pytest.raises(BackendConfigurationError, match='Unknown media backend'):
        get_media_backend('jellyfin')
