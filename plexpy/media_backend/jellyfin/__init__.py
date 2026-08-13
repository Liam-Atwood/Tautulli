# -*- coding: utf-8 -*-

"""Jellyfin transport and normalized backend primitives."""

from plexpy.media_backend.jellyfin.auth import build_authorization_header
from plexpy.media_backend.jellyfin.client import JellyfinClient, JellyfinImage
from plexpy.media_backend.jellyfin.versions import (
    JellyfinApi10_10, JellyfinApi10_11, select_api_profile,
)
from plexpy.media_backend.jellyfin.backend import JellyfinBackend
from plexpy.media_backend.jellyfin.metadata import (
    JellyfinMetadataAdapter, make_image_reference, map_item_type, parse_image_reference,
)
from plexpy.media_backend.jellyfin.activity import (
    DEFAULT_LOCAL_NETWORKS, JellyfinActivityNormalizer, classify_endpoint, stable_session_key,
)
from plexpy.media_backend.jellyfin.websocket import JellyfinWebSocketClient, websocket_url

__all__ = (
    'JellyfinClient', 'JellyfinImage', 'JellyfinApi10_10', 'JellyfinApi10_11',
    'build_authorization_header', 'select_api_profile', 'JellyfinBackend', 'JellyfinMetadataAdapter',
    'make_image_reference', 'parse_image_reference', 'map_item_type',
    'DEFAULT_LOCAL_NETWORKS', 'JellyfinActivityNormalizer', 'classify_endpoint', 'stable_session_key',
    'JellyfinWebSocketClient', 'websocket_url',
)
