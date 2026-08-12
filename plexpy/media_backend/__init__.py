# -*- coding: utf-8 -*-

"""Stable media-server boundary used by Tautulli business logic."""

from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities
from plexpy.media_backend.factory import get_media_backend
from plexpy.media_backend.idmap import (
    ENTITY_COLLECTION, ENTITY_DEVICE, ENTITY_ITEM, ENTITY_LIBRARY, ENTITY_PLAYLIST, ENTITY_TYPES,
    ENTITY_USER, ExternalIdMapper, IdentityMappingError, IdentityMappingExhaustedError,
)

__all__ = (
    'BackendCapabilities', 'MediaBackend', 'get_media_backend', 'ExternalIdMapper',
    'IdentityMappingError', 'IdentityMappingExhaustedError', 'ENTITY_TYPES', 'ENTITY_ITEM',
    'ENTITY_USER', 'ENTITY_LIBRARY', 'ENTITY_COLLECTION', 'ENTITY_PLAYLIST', 'ENTITY_DEVICE',
)
