# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCapabilities:
    websocket_sessions: bool = False
    remote_session_stop: bool = False
    exact_buffer_events: bool = False
    live_tv: bool = False
    playlists: bool = False
    collections: bool = False
    server_update_status: bool = False
    remote_access_probe: bool = False
    offline_download_inventory: bool = False
    active_client_messages: bool = False
    exact_tls_session_state: bool = False
    exact_relay_state: bool = False
