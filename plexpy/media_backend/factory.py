# -*- coding: utf-8 -*-

from plexpy.media_backend.errors import BackendConfigurationError


def get_media_backend(name='plex', **connection_options):
    """Return a fresh backend instance without importing transports eagerly."""
    if name != 'plex':
        raise BackendConfigurationError("Unknown media backend: {!r}".format(name))

    # Lazy import is required because pmsconnect participates in existing cycles
    # with users, libraries, activity processing, and notification modules.
    from plexpy.media_backend.plex import PlexBackend
    return PlexBackend(**connection_options)
