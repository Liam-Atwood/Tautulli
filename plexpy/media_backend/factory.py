# -*- coding: utf-8 -*-

from plexpy.media_backend.errors import BackendConfigurationError


def get_media_backend(name=None, **connection_options):
    """Return a fresh backend instance without importing transports eagerly."""
    if name is None:
        import plexpy
        name = getattr(plexpy.CONFIG, 'MEDIA_SERVER_TYPE', 'plex') if plexpy.CONFIG else 'plex'
    name = str(name).strip().lower()

    if name == 'plex':
        from plexpy.media_backend.plex import PlexBackend
        return PlexBackend(**connection_options)
    if name == 'jellyfin':
        from plexpy.media_backend.jellyfin.backend import JellyfinBackend
        return JellyfinBackend(**connection_options)
    raise BackendConfigurationError("Unknown media backend: {!r}".format(name))
