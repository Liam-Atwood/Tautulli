# -*- coding: utf-8 -*-

import hashlib
from io import BytesIO

import plexpy
from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities
from plexpy.media_backend.errors import (
    BackendConfigurationError, BackendFeatureUnsupportedError, BackendServerError,
)
from plexpy.media_backend.idmap import (
    ExternalIdMapper, ENTITY_COLLECTION, ENTITY_LIBRARY, ENTITY_PLAYLIST, ENTITY_USER,
)
from plexpy.media_backend.jellyfin.client import JellyfinClient, JellyfinImage
from plexpy.media_backend.jellyfin.metadata import JellyfinMetadataAdapter, parse_image_reference
from plexpy.media_backend.jellyfin.activity import JellyfinActivityNormalizer


JELLYFIN_CAPABILITIES = BackendCapabilities(
    websocket_sessions=True, playlists=True, collections=True)


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
    def get_recently_added(self, **kwargs):
        return self.get_recently_added_details(**kwargs)

    def get_recently_added_details(self, start='0', count='0', media_type='', section_id='', **kwargs):
        self._ensure_connected()
        start, count = max(0, int(start or 0)), max(0, int(count or 0))
        type_map = {
            'movie': ('Movie',), 'show': ('Series',), 'artist': ('MusicArtist',),
            'other_video': ('Video', 'Trailer', 'MusicVideo'),
        }
        include_types = type_map.get(media_type) if media_type else tuple(
            value for values in type_map.values() for value in values)
        parent_id = None
        if section_id:
            parent_id = self.mapper.to_external(ENTITY_LIBRARY, section_id)
            if parent_id is None:
                return {'recently_added': []}
        result = self.client.get_latest_items(
            start=start, limit=count or 50, parent_id=parent_id,
            include_item_types=include_types)
        items = result.get('Items', []) if isinstance(result, dict) else result or []
        normalized = []
        for item in items:
            external_id = str(item.get('Id') or '')
            if not external_id:
                continue
            try:
                normalized.append(self.metadata.get_metadata(external_id))
            except BackendFeatureUnsupportedError:
                continue
        normalized.sort(key=lambda value: (int(value.get('added_at') or 0),
                                            str(value.get('external_item_id') or '')), reverse=True)
        return {'recently_added': normalized[:count or None]}
    def get_libraries(self):
        self._ensure_connected()
        output = []
        type_map = {
            'movies': ('movie', 'Movie', None, None),
            'tvshows': ('show', 'Series', 'Season', 'Episode'),
            'music': ('artist', 'MusicArtist', 'MusicAlbum', 'Audio'),
            'photos': ('photo', 'PhotoAlbum', None, 'Photo'),
            'homevideos': ('movie', 'Video', None, None),
            'mixed': ('movie', None, None, None),
        }
        for library in self.client.get_libraries() or []:
            external_id = str(library.get('ItemId') or '')
            if not external_id:
                continue
            section_type, count_type, parent_type, child_type = type_map.get(
                str(library.get('CollectionType') or 'mixed').lower(), ('movie', None, None, None))
            output.append({
                'section_id': self.mapper.get_or_create(ENTITY_LIBRARY, external_id),
                'external_library_id': external_id,
                'section_name': library.get('Name') or '', 'section_type': section_type,
                'agent': 'jellyfin', 'thumb': '', 'art': '', 'is_active': 1,
                'count': self.client.get_library_count(external_id, count_type),
                'parent_count': (self.client.get_library_count(external_id, parent_type)
                                 if parent_type else None),
                'child_count': (self.client.get_library_count(external_id, child_type)
                                if child_type else None),
            })
        return output

    def get_users(self):
        self._ensure_connected()
        libraries = {str(library.get('ItemId')): self.mapper.get_or_create(
            ENTITY_LIBRARY, str(library.get('ItemId'))) for library in self.client.get_libraries() or []
                     if library.get('ItemId')}
        output = []
        for user in self.client.get_users() or []:
            external_id = str(user.get('Id') or '')
            if not external_id:
                continue
            policy = user.get('Policy') or {}
            shared = list(libraries.values()) if policy.get('EnableAllFolders') else [
                libraries[value] for value in policy.get('EnabledFolders') or [] if value in libraries]
            output.append({
                'user_id': self.mapper.get_or_create(ENTITY_USER, external_id),
                'external_user_id': external_id, 'username': user.get('Name') or '',
                'friendly_name': user.get('Name') or '', 'title': None, 'email': '',
                'thumb': ('jellyfin://user/{}/Primary/0'.format(external_id)
                          if user.get('PrimaryImageTag') else ''),
                'is_active': int(not policy.get('IsDisabled', False)),
                'is_admin': int(bool(policy.get('IsAdministrator'))), 'is_home_user': 1,
                'is_allow_sync': int(bool(policy.get('EnableContentDownloading'))),
                'is_restricted': int(not bool(policy.get('EnableAllFolders'))),
                'shared_libraries': shared, 'filter_all': '', 'filter_movies': '',
                'filter_tv': '', 'filter_music': '', 'filter_photos': '',
            })
        return output

    def get_library_details(self):
        return self.get_libraries()
    def search(self, query, **kwargs):
        return self.get_search_results(query=query, limit=kwargs.get('limit', ''),
                                       user_id=kwargs.get('user_id'))

    def get_search_results(self, query='', limit='', user_id=None):
        groups = {key: [] for key in (
            'movie', 'show', 'season', 'episode', 'artist', 'album', 'track', 'collection')}
        if not str(query or '').strip():
            return {'results_count': 0, 'results_list': groups}
        result = self.client.search_items(
            str(query).strip(), limit=int(limit or 50), user_id=user_id,
            include_item_types='Movie,Series,Season,Episode,MusicArtist,MusicAlbum,Audio,BoxSet')
        for item in (result or {}).get('Items', []):
            try:
                metadata = self.metadata.get_metadata(item['Id'], user_id=user_id)
            except (KeyError, BackendFeatureUnsupportedError):
                continue
            if metadata['media_type'] in groups:
                groups[metadata['media_type']].append(metadata)
        return {'results_count': sum(len(values) for values in groups.values()),
                'results_list': groups}
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
    def _normalize_container_list(self, result, entity, user_id=None, section_id=None):
        output = []
        for item in (result or {}).get('Items', []):
            metadata = self.metadata.get_metadata(item['Id'], user_id=user_id, media_info=False)
            metadata['rating_key'] = self.mapper.get_or_create(entity, str(item['Id']))
            metadata['child_count'] = item.get('ChildCount', '')
            metadata['section_id'] = section_id or metadata.get('section_id')
            output.append(metadata)
        return output

    def get_playlists(self, **kwargs):
        result = self.client.get_playlists(user_id=kwargs.get('user_id'), limit=kwargs.get('limit', 100))
        return self._normalize_container_list(
            result, ENTITY_PLAYLIST, user_id=kwargs.get('user_id'), section_id=kwargs.get('section_id'))

    def get_collections(self, **kwargs):
        section_id = kwargs.get('section_id')
        external_library = self.mapper.to_external(ENTITY_LIBRARY, section_id) if section_id else None
        result = self.client.get_collections(
            parent_id=external_library, user_id=kwargs.get('user_id'), limit=kwargs.get('limit', 100))
        return self._normalize_container_list(
            result, ENTITY_COLLECTION, user_id=kwargs.get('user_id'), section_id=section_id)
    def get_server_update_status(self): self._unsupported('Server update status')
