# -*- coding: utf-8 -*-

import time
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from plexpy import common
from plexpy import logger
from plexpy.media_backend.errors import (
    BackendAuthError, BackendConfigurationError, BackendConnectionError, BackendNotFoundError,
    BackendRateLimitError, BackendServerError,
)
from plexpy.media_backend.jellyfin.auth import build_authorization_header
from plexpy.media_backend.jellyfin.versions import select_api_profile


_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class JellyfinImage:
    data: bytes
    content_type: str = None
    etag: str = None


def normalize_base_url(base_url):
    raw_url = str(base_url or '').strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in raw_url):
        raise BackendConfigurationError('Jellyfin server URL contains invalid characters')
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise BackendConfigurationError('Invalid Jellyfin server URL') from error
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
        raise BackendConfigurationError('Jellyfin server URL must use HTTP or HTTPS')
    if parsed.username is not None or parsed.password is not None:
        raise BackendConfigurationError('Jellyfin server URL cannot contain credentials')
    if parsed.query or parsed.fragment:
        raise BackendConfigurationError('Jellyfin server URL cannot contain a query or fragment')
    hostname = parsed.hostname
    if ':' in hostname and not hostname.startswith('['):
        hostname = '[{}]'.format(hostname)
    netloc = '{}:{}'.format(hostname, port) if port is not None else hostname
    path = parsed.path.rstrip('/')
    return urlunsplit((parsed.scheme.lower(), netloc, path, '', ''))


def _comma_list(value):
    if isinstance(value, (list, tuple, set, frozenset)):
        return ','.join(str(item) for item in value)
    return value


class JellyfinClient:
    """Small JSON-first client for the supported Jellyfin API families."""

    def __init__(self, base_url, token, verify_ssl=True, timeout=(5, 30), trace=False,
                 client_name=common.PRODUCT, client_version=common.RELEASE,
                 device_name='Tautulli', device_id='tautulli-jellyfin', session=None):
        self.base_url = normalize_base_url(base_url)
        self.verify_ssl = bool(verify_ssl)
        self.timeout = self._normalize_timeout(timeout)
        self.trace = bool(trace)
        self._session = session or requests.Session()
        self._owns_session = session is None
        authorization = build_authorization_header(
            token=token, client=client_name, device=device_name,
            device_id=device_id, version=client_version)
        self._session.headers.update({
            'Accept': 'application/json',
            'Accept-Charset': 'UTF-8,*',
            'Authorization': authorization,
            'User-Agent': common.USER_AGENT,
            'X-Application': '{}/{}'.format(client_name, client_version),
        })
        retry = Retry(
            total=2, connect=2, read=2, status=2, backoff_factor=0.25,
            status_forcelist=sorted(_RETRY_STATUSES), allowed_methods=frozenset({'GET', 'HEAD'}),
            respect_retry_after_header=True, raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)
        self._server_id = None
        self._server_version = None
        self._api_profile = None

    @staticmethod
    def _normalize_timeout(timeout):
        if isinstance(timeout, (int, float)):
            timeout = (timeout, timeout)
        if not isinstance(timeout, (tuple, list)) or len(timeout) != 2:
            raise BackendConfigurationError('timeout must be a number or connect/read pair')
        try:
            timeout = tuple(float(value) for value in timeout)
        except (TypeError, ValueError) as error:
            raise BackendConfigurationError('timeout values must be positive numbers') from error
        if any(value <= 0 for value in timeout):
            raise BackendConfigurationError('timeout values must be positive numbers')
        return timeout

    @property
    def server_id(self):
        return self._server_id

    @property
    def server_version(self):
        return self._server_version

    @property
    def api_profile(self):
        return self._api_profile

    @property
    def session(self):
        return self._session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self._owns_session:
            self._session.close()

    def _url(self, endpoint):
        return '{}/{}'.format(self.base_url, str(endpoint).lstrip('/'))

    def _request(self, method, endpoint, params=None, expect_image=False):
        method = method.upper()
        url = self._url(endpoint)
        started = time.monotonic()
        status = None
        try:
            response = self._session.request(
                method, url, params=params, timeout=self.timeout, verify=self.verify_ssl)
            status = response.status_code
        except (requests.exceptions.Timeout, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as error:
            raise BackendConnectionError(
                'Unable to connect to Jellyfin', endpoint=url) from error
        except requests.exceptions.RequestException as error:
            raise BackendConnectionError(
                'Jellyfin request failed', endpoint=url) from error
        finally:
            if self.trace:
                logger.debug(
                    'Tautulli JellyfinClient :: %s %s completed status=%s in %d ms.', method, url,
                    status if status is not None else 'connection-error',
                    int((time.monotonic() - started) * 1000))

        self._raise_for_status(response, url)
        if response.status_code == 204:
            return None
        if expect_image:
            return JellyfinImage(
                data=response.content,
                content_type=response.headers.get('Content-Type'),
                etag=response.headers.get('ETag'),
            )
        try:
            return response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as error:
            raise BackendServerError(
                'Jellyfin returned malformed JSON', endpoint=url,
                status_code=response.status_code) from error

    @staticmethod
    def _raise_for_status(response, endpoint):
        status = response.status_code
        if 200 <= status < 300:
            return
        if status in (401, 403):
            raise BackendAuthError('Jellyfin authentication failed', endpoint=endpoint, status_code=status)
        if status == 404:
            raise BackendNotFoundError('Jellyfin resource was not found', endpoint=endpoint, status_code=status)
        if status == 429:
            raise BackendRateLimitError(
                'Jellyfin rate limit exceeded', endpoint=endpoint, status_code=status,
                retry_after=response.headers.get('Retry-After'))
        if status == 409:
            raise BackendServerError('Jellyfin request conflicted', endpoint=endpoint, status_code=status)
        if status >= 500:
            raise BackendServerError('Jellyfin server error', endpoint=endpoint, status_code=status)
        raise BackendServerError('Jellyfin request was rejected', endpoint=endpoint, status_code=status)

    def connect(self):
        info = self.get_system_info()
        if not isinstance(info, dict) or not info.get('Id') or not info.get('Version'):
            raise BackendServerError('Jellyfin system information is incomplete')
        profile = select_api_profile(info['Version'])
        self._server_id = str(info['Id'])
        self._server_version = str(info['Version'])
        self._api_profile = profile
        return info

    def get_system_info(self):
        return self._request('GET', 'System/Info')

    def get_sessions(self, **params):
        return self._request('GET', 'Sessions', params=params or None)

    def get_item(self, item_id, user_id=None, fields=None):
        params = {}
        if user_id is not None:
            params['userId'] = user_id
        if fields is not None:
            params['fields'] = _comma_list(fields)
        return self._request(
            'GET', 'Items/{}'.format(quote(str(item_id), safe='')), params=params or None)

    def get_items(self, **params):
        params = {key: _comma_list(value) for key, value in params.items() if value is not None}
        return self._request('GET', 'Items', params=params or None)

    def get_users(self):
        return self._request('GET', 'Users')

    def get_libraries(self):
        return self._request('GET', 'Library/VirtualFolders')

    def get_image(self, item_id, image_type='Primary', image_index=0, **params):
        endpoint = 'Items/{}/Images/{}/{}'.format(
            quote(str(item_id), safe=''), quote(str(image_type), safe=''), int(image_index))
        return self._request('GET', endpoint, params=params or None, expect_image=True)
