# -*- coding: utf-8 -*-

"""Standalone Jellyfin transport primitives.

Runtime backend selection remains Plex-only until the Phase 4 configuration
and onboarding work is complete.
"""

from plexpy.media_backend.jellyfin.auth import build_authorization_header
from plexpy.media_backend.jellyfin.client import JellyfinClient, JellyfinImage
from plexpy.media_backend.jellyfin.versions import (
    JellyfinApi10_10, JellyfinApi10_11, select_api_profile,
)

__all__ = (
    'JellyfinClient', 'JellyfinImage', 'JellyfinApi10_10', 'JellyfinApi10_11',
    'build_authorization_header', 'select_api_profile',
)
