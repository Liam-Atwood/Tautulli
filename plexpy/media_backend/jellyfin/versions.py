# -*- coding: utf-8 -*-

import re
from dataclasses import dataclass

from plexpy.media_backend.errors import BackendFeatureUnsupportedError, BackendServerError


@dataclass(frozen=True)
class JellyfinApiProfile:
    name: str
    minimum_version: tuple


class JellyfinApi10_10(JellyfinApiProfile):
    def __init__(self):
        JellyfinApiProfile.__init__(self, name='10.10', minimum_version=(10, 10, 7))


class JellyfinApi10_11(JellyfinApiProfile):
    def __init__(self):
        JellyfinApiProfile.__init__(self, name='10.11', minimum_version=(10, 11, 0))


def parse_server_version(version):
    match = re.match(r'^\s*(\d+)\.(\d+)\.(\d+)', str(version or ''))
    if not match:
        raise BackendServerError('Jellyfin returned an invalid server version')
    return tuple(int(part) for part in match.groups())


def select_api_profile(version):
    parsed = parse_server_version(version)
    if parsed >= (12, 0, 0):
        raise BackendFeatureUnsupportedError(
            'Jellyfin 12 and newer require a dedicated API implementation')
    if parsed >= (10, 11, 0):
        return JellyfinApi10_11()
    if parsed >= (10, 10, 7):
        return JellyfinApi10_10()
    raise BackendFeatureUnsupportedError(
        'Jellyfin versions older than 10.10.7 are unsupported')
