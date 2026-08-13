# -*- coding: utf-8 -*-

import threading
import time
from enum import Enum

import requests

from plexpy.media_backend.errors import (
    BackendAuthError, BackendConnectionError, BackendFeatureUnsupportedError, BackendServerError,
)


class HealthState(str, Enum):
    UP = 'UP'
    SUSPECT = 'SUSPECT'
    DOWN = 'DOWN'
    AUTH_FAILED = 'AUTH_FAILED'
    UNSUPPORTED_VERSION = 'UNSUPPORTED_VERSION'


class BackendHealth:
    def __init__(self, failure_threshold=2):
        self.failure_threshold = max(2, int(failure_threshold))
        self.failures = 0
        self.state = HealthState.SUSPECT

    def success(self):
        self.failures, self.state = 0, HealthState.UP
        return self.state

    def failure(self, error):
        if isinstance(error, BackendAuthError):
            self.state = HealthState.AUTH_FAILED
        elif isinstance(error, BackendFeatureUnsupportedError):
            self.state = HealthState.UNSUPPORTED_VERSION
        else:
            self.failures += 1
            self.state = (HealthState.DOWN if self.failures >= self.failure_threshold
                          else HealthState.SUSPECT)
        return self.state


class JellyfinReleaseMonitor:
    URL = 'https://api.github.com/repos/jellyfin/jellyfin/releases/latest'

    def __init__(self, cache_seconds=21600, session=None):
        self.cache_seconds = int(cache_seconds)
        self.session = session or requests.Session()
        self._cache = None
        self._lock = threading.Lock()

    @staticmethod
    def _version(value):
        try: return tuple(int(part) for part in str(value).lstrip('v').split('.')[:3])
        except ValueError: return ()

    def check(self, current_version):
        now = time.monotonic()
        with self._lock:
            if self._cache and now - self._cache[0] < self.cache_seconds:
                release = self._cache[1]
            else:
                try:
                    response = self.session.get(
                        self.URL, timeout=(5, 15), headers={'Accept': 'application/vnd.github+json'})
                    response.raise_for_status()
                    release = response.json()
                except (requests.RequestException, ValueError) as error:
                    if self._cache:
                        release = self._cache[1]
                    else:
                        raise BackendConnectionError('Unable to check Jellyfin releases') from error
                if release.get('draft') or release.get('prerelease'):
                    raise BackendServerError('Official Jellyfin release feed returned no stable release')
                self._cache = (now, release)
        latest = str(release.get('tag_name') or '').lstrip('v')
        return {'current_version': str(current_version), 'latest_version': latest,
                'update_available': self._version(latest) > self._version(current_version),
                'release_url': release.get('html_url', ''), 'feed_status': 'ok'}
