from types import SimpleNamespace

import plexpy
from plexpy import notification_handler, notifiers
from plexpy.media_backend.jellyfin.notifications import (
    DISABLED_AGENTS, FULL, NOT_APPLICABLE, REQUIRES_TELEMETRY, TRIGGER_CAPABILITIES,
    trigger_available,
)


def test_every_existing_trigger_is_classified():
    existing = {action['name'] for action in notifiers.available_notification_actions()}
    assert existing == set(TRIGGER_CAPABILITIES)
    assert TRIGGER_CAPABILITIES['on_buffer'] == REQUIRES_TELEMETRY
    assert TRIGGER_CAPABILITIES['on_extdown'] == NOT_APPLICABLE
    for action in ('on_play', 'on_stop', 'on_pause', 'on_resume', 'on_watched', 'on_change',
                   'on_concurrent', 'on_newdevice', 'on_created', 'on_intdown', 'on_intup',
                   'on_tokenexpired', 'on_pmsupdate'):
        assert TRIGGER_CAPABILITIES[action] == FULL


def test_plex_cloud_agents_hidden_without_changing_stored_config(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(MEDIA_SERVER_TYPE='jellyfin'))
    visible = {agent['name'] for agent in notifiers.available_notification_agents()}
    assert DISABLED_AGENTS.isdisjoint(visible)
    monkeypatch.setattr(plexpy.CONFIG, 'MEDIA_SERVER_TYPE', 'plex')
    restored = {agent['name'] for agent in notifiers.available_notification_agents()}
    assert DISABLED_AGENTS <= restored


def test_stock_jellyfin_drops_buffer_error_marker_and_external_events(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(MEDIA_SERVER_TYPE='jellyfin'))
    calls = []
    monkeypatch.setattr(notifiers, 'get_notifiers', lambda **kwargs: calls.append(kwargs) or [])
    for action in ('on_buffer', 'on_error', 'on_intro', 'on_commercial', 'on_credits',
                   'on_extdown', 'on_extup'):
        assert trigger_available(action) is False
        notification_handler.add_notifier_each(notify_action=action, stream_data={})
    assert calls == []


def test_generic_agents_remain_available_for_jellyfin(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(MEDIA_SERVER_TYPE='jellyfin'))
    visible = {agent['name'] for agent in notifiers.available_notification_agents()}
    assert {'email', 'discord', 'telegram', 'slack', 'webhook', 'mqtt', 'pushover',
            'gotify', 'scripts', 'browser'} <= visible
