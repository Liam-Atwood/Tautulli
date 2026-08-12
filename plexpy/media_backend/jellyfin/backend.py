# -*- coding: utf-8 -*-

import plexpy
from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities
from plexpy.media_backend.errors import BackendConfigurationError, BackendFeatureUnsupportedError
from plexpy.media_backend.idmap import ExternalIdMapper
from plexpy.media_backend.jellyfin.client import JellyfinClient


JELLYFIN_CAPABILITIES = BackendCapabilities()


class JellyfinBackend(MediaBackend):
    """Configured Jellyfin backend. Normalizers are attached in Phases 5 and 6."""

    def __init__(self, url=None, token=None, verify_ssl=None, server_id=None, timeout=None,
                 database_file=None, client=None):
        config = plexpy.CONFIG
        self.url = url if url is not None else getattr(config, 'MEDIA_SERVER_URL', '')
        self.token = token if token is not None else getattr(config, 'MEDIA_SERVER_TOKEN', '')
        self.ssl_verify = (getattr(config, 'MEDIA_SERVER_VERIFY_TLS', True)
                           if verify_ssl is None else bool(verify_ssl))
        self.timeout = timeout if timeout is not None else getattr(config, 'PMS_TIMEOUT', 15)
        self._configured_server_id = str(
            server_id if server_id is not None else getattr(config, 'MEDIA_SERVER_ID', '') or '')
        if not self.url or not self.token:
            raise BackendConfigurationError('Jellyfin URL and token are required')
        self.client = client or JellyfinClient(
            self.url, self.token, verify_ssl=self.ssl_verify, timeout=self.timeout)
        self.request_handler = self.client
        self._database_file = database_file
        self._mapper = None
        self._metadata = None
        self._activity = None

    @property
    def capabilities(self):
        return JELLYFIN_CAPABILITIES

    @property
    def mapper(self):
        self._ensure_connected()
        if self._mapper is None:
            self._mapper = ExternalIdMapper('jellyfin', self.client.server_id, self._database_file)
        return self._mapper

    @property
    def metadata(self):
        self._unsupported('Metadata')

    def _ensure_connected(self):
        if self.client.server_id is None:
            self.client.connect()
        if self._configured_server_id and self.client.server_id != self._configured_server_id:
            raise BackendConfigurationError('Connected Jellyfin server identity does not match configuration')

    def get_server_info(self):
        self._ensure_connected()
        info = self.client.get_system_info()
        return {
            'media_backend': 'jellyfin',
            'machine_identifier': self.client.server_id,
            'name': info.get('ServerName', ''),
            'version': self.client.server_version,
            'platform': info.get('OperatingSystem', ''),
        }

    def _unsupported(self, operation):
        raise BackendFeatureUnsupportedError(
            '{} is not available for Jellyfin in this build'.format(operation))

    def get_current_activity(self, skip_cache=False):
        self._unsupported('Current activity')
    def get_metadata_details(self, local_item_id, **kwargs):
        self._unsupported('Metadata')
    def get_item_children(self, local_item_id, **kwargs):
        self._unsupported('Item children')
    def get_recently_added(self, **kwargs): self._unsupported('Recently added')
    def get_libraries(self): self._unsupported('Libraries')
    def get_users(self): self._unsupported('Users')
    def search(self, query, **kwargs): self._unsupported('Search')
    def get_image(self, image_ref, **kwargs):
        self._unsupported('Images')
    def terminate_session(self, session_id, message=None): self._unsupported('Session termination')
    def get_devices(self): self._unsupported('Devices')
    def get_playlists(self, **kwargs): self._unsupported('Playlists')
    def get_collections(self, **kwargs): self._unsupported('Collections')
    def get_server_update_status(self): self._unsupported('Server update status')
