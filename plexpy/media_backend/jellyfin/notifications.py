# -*- coding: utf-8 -*-

FULL = 'FULL'
NOT_APPLICABLE = 'N/A'
REQUIRES_TELEMETRY = 'REQUIRES TELEMETRY'

TRIGGER_CAPABILITIES = {
    'on_play': FULL, 'on_stop': FULL, 'on_pause': FULL, 'on_resume': FULL,
    'on_change': FULL, 'on_watched': FULL, 'on_concurrent': FULL,
    'on_newdevice': FULL, 'on_created': FULL, 'on_intdown': FULL,
    'on_intup': FULL, 'on_tokenexpired': FULL, 'on_pmsupdate': FULL,
    'on_buffer': REQUIRES_TELEMETRY,
    'on_error': NOT_APPLICABLE, 'on_intro': NOT_APPLICABLE,
    'on_commercial': NOT_APPLICABLE, 'on_credits': NOT_APPLICABLE,
    'on_extdown': NOT_APPLICABLE, 'on_extup': NOT_APPLICABLE,
    # Tautulli-owned events are backend-independent.
    'on_plexpyupdate': FULL, 'on_plexpydbcorrupt': FULL,
}

DISABLED_AGENTS = frozenset({'plex', 'plexmobileapp'})


def trigger_status(action):
    return TRIGGER_CAPABILITIES.get(action, NOT_APPLICABLE)


def trigger_available(action):
    return trigger_status(action) == FULL


def agent_available(agent_name):
    return agent_name not in DISABLED_AGENTS
