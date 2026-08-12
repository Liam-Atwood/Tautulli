import inspect
from dataclasses import FrozenInstanceError

import pytest
import plexpy

from plexpy import pmsconnect
from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities
from plexpy.media_backend.errors import (
    BackendConfigurationError, BackendFeatureUnsupportedError, BackendRateLimitError)
from plexpy.media_backend import factory


def public_methods(cls):
    return {
        name: member for name, member in cls.__dict__.items()
        if callable(member) and not name.startswith('_')
    }


def test_facade_preserves_every_legacy_public_signature():
    legacy = public_methods(pmsconnect._LegacyPmsConnect)
    facade = public_methods(pmsconnect.PmsConnect)
    assert set(facade) == set(legacy)
    for name, method in legacy.items():
        assert inspect.signature(facade[name]) == inspect.signature(method), name


def test_facade_exposes_connection_attributes_and_forwards(monkeypatch):
    calls = []

    class FakeLegacy:
        url = 'http://fixture.invalid'
        token = 'secret'
        timeout = 15
        ssl_verify = True
        request_handler = object()

    class FakeBackend:
        legacy = FakeLegacy()

        def get_current_activity(self, skip_cache=False):
            calls.append(skip_cache)
            return {'stream_count': '0', 'sessions': []}

    monkeypatch.setattr(factory, 'get_media_backend', lambda **kwargs: FakeBackend())
    facade = pmsconnect.PmsConnect()
    assert facade.get_current_activity(skip_cache=True) == {'stream_count': '0', 'sessions': []}
    assert calls == [True]
    assert (facade.url, facade.token, facade.timeout, facade.ssl_verify) == (
        'http://fixture.invalid', 'secret', 15, True)
    assert facade.request_handler is FakeBackend.legacy.request_handler


def test_capabilities_are_complete_and_immutable():
    capabilities = BackendCapabilities()
    assert len(capabilities.__dataclass_fields__) == 12
    with pytest.raises(FrozenInstanceError):
        capabilities.live_tv = True


def test_media_backend_declares_canonical_surface():
    expected = {
        'get_server_info', 'get_current_activity', 'get_metadata_details', 'get_item_children',
        'get_recently_added', 'get_libraries', 'get_users', 'search', 'get_image',
        'terminate_session', 'get_devices', 'get_playlists', 'get_collections',
        'get_server_update_status', 'capabilities',
    }
    assert expected <= set(MediaBackend.__abstractmethods__)


def test_factory_rejects_unknown_backends():
    with pytest.raises(BackendConfigurationError, match='Unknown media backend'):
        factory.get_media_backend('emby')


def test_factory_returns_fresh_plex_backends(monkeypatch):
    class FakeLegacy:
        def __init__(self, url=None, token=None):
            self.url, self.token = url, token

    monkeypatch.setattr(pmsconnect, '_LegacyPmsConnect', FakeLegacy)
    first = factory.get_media_backend(url='http://one.invalid', token='one')
    second = factory.get_media_backend(url='http://two.invalid', token='two')
    assert first is not second and first.legacy is not second.legacy
    assert (first.legacy.url, second.legacy.url) == ('http://one.invalid', 'http://two.invalid')


def test_factory_uses_configured_backend_and_returns_fresh_jellyfin(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', type('Config', (), {
        'MEDIA_SERVER_TYPE': 'jellyfin', 'MEDIA_SERVER_URL': 'http://jellyfin.invalid',
        'MEDIA_SERVER_TOKEN': 'token', 'MEDIA_SERVER_VERIFY_TLS': True,
        'MEDIA_SERVER_ID': '', 'PMS_TIMEOUT': 15,
    })())
    first = factory.get_media_backend()
    second = factory.get_media_backend()
    assert first.__class__.__name__ == 'JellyfinBackend'
    assert first is not second and first.client is not second.client
    first.client.close()
    second.client.close()


def test_backend_errors_redact_secrets_and_keep_context():
    error = BackendRateLimitError(
        'Rate limited', endpoint='https://fixture.invalid/Sessions?api_key=secret&user=test',
        status_code=429, retry_after=30)
    rendered = str(error)
    assert 'secret' not in rendered
    assert 'api_key=<redacted>' in rendered
    assert 'status=429' in rendered and 'retry_after=30' in rendered
    assert issubclass(BackendFeatureUnsupportedError, Exception)
    assert 'raw-secret' not in str(BackendConfigurationError('Authorization: raw-secret'))
