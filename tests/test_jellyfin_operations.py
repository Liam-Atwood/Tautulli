from types import SimpleNamespace

import pytest

import plexpy
from plexpy.media_backend.errors import (
    BackendAuthError, BackendConfigurationError, BackendConnectionError,
    BackendFeatureUnsupportedError,
)
from plexpy.media_backend.jellyfin.backend import JellyfinBackend
from plexpy.media_backend.jellyfin.client import JellyfinClient
from plexpy.media_backend.jellyfin.operations import BackendHealth, HealthState, JellyfinReleaseMonitor


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class Session:
    def __init__(self, payload): self.payload, self.calls = payload, 0
    def get(self, *args, **kwargs): self.calls += 1; return Response(self.payload)


def test_health_thresholds_and_distinct_terminal_states():
    health = BackendHealth()
    assert health.success() == HealthState.UP
    assert health.failure(BackendConnectionError('one')) == HealthState.SUSPECT
    assert health.failure(BackendConnectionError('two')) == HealthState.DOWN
    assert health.success() == HealthState.UP
    assert health.failure(BackendAuthError('auth')) == HealthState.AUTH_FAILED
    assert health.failure(BackendFeatureUnsupportedError('version')) == HealthState.UNSUPPORTED_VERSION


def test_stable_release_comparison_and_cache():
    session = Session({'tag_name': 'v10.11.12', 'html_url': 'https://github.com/jellyfin/jellyfin/releases/tag/v10.11.12',
                       'draft': False, 'prerelease': False})
    monitor = JellyfinReleaseMonitor(session=session)
    result = monitor.check('10.11.11')
    assert result['update_available'] is True and result['latest_version'] == '10.11.12'
    assert monitor.check('10.11.12')['update_available'] is False
    assert session.calls == 1


def test_stop_devices_logs_and_log_path_validation(monkeypatch):
    calls = []
    class Client:
        server_id = 'server-a'; server_version = '10.11.11'
        def stop_session(self, value): calls.append(value); return True
        def get_devices(self): return {'Items': [{'Id': 'device-a', 'Name': 'TV', 'LastUserName': 'Ada'}]}
        def get_logs(self): return [{'Name': 'log.txt'}]
        def get_log(self, name): return b'x' * 10
    class Mapper:
        def get_or_create(self, entity, external): return 42
    backend = object.__new__(JellyfinBackend)
    backend.client, backend._mapper = Client(), Mapper()
    backend._configured_server_id = ''
    assert backend.terminate_session('session-a') is True and calls == ['session-a']
    assert backend.get_devices()[0]['device_id'] == 42
    assert backend.get_server_logs() == [{'Name': 'log.txt'}]
    assert backend.get_server_log('log.txt', max_bytes=4) == b'xxxx'

    client = object.__new__(JellyfinClient)
    with pytest.raises(BackendConfigurationError):
        JellyfinClient.get_log(client, '../secret')


def test_capabilities_do_not_claim_external_probe_or_telemetry():
    capabilities = JellyfinBackend.capabilities.fget(object.__new__(JellyfinBackend))
    assert capabilities.remote_session_stop and capabilities.live_tv
    assert capabilities.playlists and capabilities.collections and capabilities.server_update_status
    assert capabilities.remote_access_probe is False and capabilities.exact_buffer_events is False
