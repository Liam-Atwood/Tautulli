# -*- coding: utf-8 -*-

"""Stable media-server boundary used by Tautulli business logic."""

from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities
from plexpy.media_backend.factory import get_media_backend

__all__ = ('BackendCapabilities', 'MediaBackend', 'get_media_backend')
