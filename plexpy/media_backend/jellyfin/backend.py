# -*- coding: utf-8 -*-

import hashlib
from io import BytesIO

import plexpy
from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities
from plexpy.media_backend.errors import (
    BackendConfigurationError, BackendFeatureUnsupportedError, BackendServerError,
)
from plexpy.media_backend.idmap import ExternalIdMapper
from plexpy.media_backend.jellyfin.client import JellyfinClient, JellyfinImage
from plexpy.media_backend.jellyfin.metadata import JellyfinMetadataAdapter, parse_image_reference
from plexpy.media_backend.jellyfin.activity import JellyfinActivityNormalizer


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
        if self._metadata is None:
            self._metadata = JellyfinMetadataAdapter(
                self.client, self.mapper, getattr(plexpy.CONFIG, 'METADATA_CACHE_SECONDS', 1800))
        return self._metadata

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
        if self._activity is None:
            self._activity = JellyfinActivityNormalizer(
                self.client, self.mapper, self.metadata, getattr(plexpy.CONFIG, 'LOCAL_NETWORKS', None))
        return self._activity.get_current_activity(skip_cache=skip_cache)
    def get_metadata_details(self, local_item_id, **kwargs):
        for legacy in ('sync_id', 'plex_guid', 'epg_key'):
            if kwargs.get(legacy):
                self._unsupported(legacy)
        allowed = {key: kwargs[key] for key in ('skip_cache', 'media_info', 'user_id') if key in kwargs}
        return self.metadata.from_local(local_item_id, **allowed)
    def get_item_children(self, local_item_id, **kwargs):
        return self.metadata.get_children(local_item_id, **kwargs)
    def get_recently_added(self, **kwargs): self._unsupported('Recently added')
    def get_libraries(self): self._unsupported('Libraries')
    def get_users(self): self._unsupported('Users')
    def search(self, query, **kwargs): self._unsupported('Search')
    def get_image(self, image_ref, **kwargs):
        _, external_id, image_type, image_index = parse_image_reference(image_ref)
        image = self.client.get_image(external_id, image_type=image_type, image_index=image_index)
        transform_keys = ('width', 'height', 'opacity', 'background', 'blur', 'img_format', 'clip')
        if not any(kwargs.get(key) not in (None, '', False) for key in transform_keys):
            return image
        return self._transform_image(image, **kwargs)

    @staticmethod
    def _transform_image(image, width=None, height=None, opacity=None, background=None,
                         blur=None, img_format='png', clip=False, **kwargs):
        try:
            from PIL import Image, ImageColor, ImageFilter, ImageOps, UnidentifiedImageError
            with Image.open(BytesIO(image.data)) as source:
                source.load()
                result = source.convert('RGBA')
                size = tuple(max(1, int(value)) for value in (
                    width or result.width, height or result.height))
                if clip:
                    result = ImageOps.fit(result, size, method=Image.Resampling.LANCZOS)
                else:
                    result.thumbnail(size, Image.Resampling.LANCZOS)
                if blur not in (None, '', 0, '0'):
                    result = result.filter(ImageFilter.GaussianBlur(radius=max(0, float(blur)) / 10.0))
                if opacity not in (None, ''):
                    alpha = result.getchannel('A').point(
                        lambda value: round(value * max(0, min(100, float(opacity))) / 100.0))
                    result.putalpha(alpha)
                if background:
                    canvas = Image.new('RGBA', result.size, ImageColor.getcolor(str(background), 'RGBA'))
                    canvas.alpha_composite(result)
                    result = canvas
                output_format = str(img_format or 'png').upper()
                if output_format == 'JPG':
                    output_format = 'JPEG'
                if output_format not in ('PNG', 'JPEG'):
                    raise ValueError('unsupported output format')
                if output_format == 'JPEG':
                    flattened = Image.new('RGB', result.size, (255, 255, 255))
                    flattened.paste(result, mask=result.getchannel('A'))
                    result = flattened
                output = BytesIO()
                result.save(output, format=output_format)
        except (OSError, ValueError, TypeError, UnidentifiedImageError) as error:
            raise BackendServerError('Unable to transform Jellyfin image') from error
        data = output.getvalue()
        return JellyfinImage(
            data=data,
            content_type='image/png' if output_format == 'PNG' else 'image/jpeg',
            etag='"{}"'.format(hashlib.sha256(data).hexdigest()),
        )
    def terminate_session(self, session_id, message=None): self._unsupported('Session termination')
    def get_devices(self): self._unsupported('Devices')
    def get_playlists(self, **kwargs): self._unsupported('Playlists')
    def get_collections(self, **kwargs): self._unsupported('Collections')
    def get_server_update_status(self): self._unsupported('Server update status')
