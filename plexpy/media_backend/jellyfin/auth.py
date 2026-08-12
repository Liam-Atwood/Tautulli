# -*- coding: utf-8 -*-

from plexpy.media_backend.errors import BackendConfigurationError


def _header_value(name, value, required=True):
    if value is None:
        value = ''
    value = str(value)
    if required and not value.strip():
        raise BackendConfigurationError('{} cannot be empty'.format(name))
    if any(character in value for character in ('\r', '\n', '"', '\\')):
        raise BackendConfigurationError('{} contains invalid header characters'.format(name))
    return value


def build_authorization_header(token, client='Tautulli', device='Tautulli',
                               device_id='tautulli-jellyfin', version='0.0.0'):
    """Build the non-legacy authorization header used by Jellyfin SDKs."""
    values = (
        ('Client', _header_value('client', client)),
        ('Device', _header_value('device', device)),
        ('DeviceId', _header_value('device_id', device_id)),
        ('Version', _header_value('version', version)),
        ('Token', _header_value('token', token)),
    )
    return 'MediaBrowser {}'.format(', '.join(
        '{}="{}"'.format(name, value) for name, value in values
    ))
