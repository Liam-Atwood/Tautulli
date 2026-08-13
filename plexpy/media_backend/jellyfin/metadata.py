# -*- coding: utf-8 -*-

from datetime import datetime
import re
import threading
import time
from urllib.parse import quote, unquote

from plexpy.media_backend.errors import BackendConfigurationError, BackendFeatureUnsupportedError
from plexpy.media_backend.idmap import ENTITY_COLLECTION, ENTITY_ITEM, ENTITY_LIBRARY, ENTITY_PLAYLIST


TYPE_MAP = {
    'Movie': 'movie', 'Series': 'show', 'Season': 'season', 'Episode': 'episode',
    'MusicArtist': 'artist', 'MusicAlbum': 'album', 'Audio': 'track', 'BoxSet': 'collection',
    'Playlist': 'playlist', 'Photo': 'photo', 'PhotoAlbum': 'photo_album',
    'Trailer': 'clip', 'MusicVideo': 'clip', 'Video': 'clip', 'LiveTvProgram': 'episode',
}
PROVIDER_SCHEMES = {
    'Imdb': 'imdb', 'Tmdb': 'tmdb', 'Tvdb': 'tvdb', 'MusicBrainzAlbum': 'musicbrainz',
    'MusicBrainzAlbumArtist': 'musicbrainz', 'MusicBrainzArtist': 'musicbrainz',
    'MusicBrainzReleaseGroup': 'musicbrainz', 'MusicBrainzTrack': 'musicbrainz',
}
IMAGE_REFERENCE = re.compile(r'^jellyfin://(item|user)/([^/]+)/(Primary|Backdrop|Banner)/(\d+)$')


def map_item_type(item):
    item_type = item.get('Type', '')
    if item_type == 'Recording':
        return 'episode' if item.get('SeriesId') or item.get('SeasonId') else 'movie'
    try:
        return TYPE_MAP[item_type]
    except KeyError as error:
        raise BackendFeatureUnsupportedError(
            'Unsupported Jellyfin item type: {!r}'.format(item_type)) from error


def make_image_reference(external_id, image_type='Primary', image_index=0, entity='item'):
    if entity not in ('item', 'user') or image_type not in ('Primary', 'Backdrop', 'Banner'):
        raise BackendConfigurationError('Invalid Jellyfin image reference')
    external_id = str(external_id or '')
    if not external_id or '/' in external_id:
        raise BackendConfigurationError('Invalid Jellyfin image identity')
    return 'jellyfin://{}/{}/{}/{}'.format(entity, quote(external_id, safe=''), image_type, int(image_index))


def parse_image_reference(reference):
    match = IMAGE_REFERENCE.fullmatch(str(reference or ''))
    if not match:
        raise BackendConfigurationError('Invalid Jellyfin image reference')
    entity, external_id, image_type, image_index = match.groups()
    return entity, unquote(external_id), image_type, int(image_index)


def _milliseconds(ticks):
    try: return str(int(ticks or 0) // 10000)
    except (TypeError, ValueError): return ''


def _epoch(value):
    if not value: return ''
    try:
        return str(int(datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()))
    except (TypeError, ValueError): return ''


def _date(value):
    return str(value or '')[:10]


class JellyfinMetadataAdapter:
    FIELDS = [
        'Path', 'Overview', 'Taglines', 'Genres', 'Tags', 'Studios', 'People', 'ProviderIds',
        'MediaSources', 'MediaStreams', 'ParentId', 'PresentationUniqueKey', 'DateCreated',
        'PremiereDate', 'ProductionYear', 'CommunityRating', 'CriticRating', 'UserData',
    ]

    def __init__(self, client, mapper, cache_seconds=1800, cache_size=256):
        self.client, self.mapper = client, mapper
        self.cache_seconds, self.cache_size = int(cache_seconds), int(cache_size)
        self._cache, self._lock = {}, threading.Lock()

    def _fetch(self, external_id, user_id=None, skip_cache=False, media_source_id=None):
        key = (self.client.server_id, str(external_id), str(user_id or ''), str(media_source_id or ''))
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if not skip_cache and cached and now - cached[0] <= self.cache_seconds:
                return cached[1]
        item = self.client.get_item(external_id, user_id=user_id, fields=self.FIELDS)
        with self._lock:
            self._cache[key] = (now, item)
            while len(self._cache) > self.cache_size:
                self._cache.pop(next(iter(self._cache)))
        return item

    def from_local(self, local_item_id, **kwargs):
        external_id = next((value for entity in (ENTITY_ITEM, ENTITY_COLLECTION, ENTITY_PLAYLIST)
                            if (value := self.mapper.to_external(entity, local_item_id)) is not None), None)
        if external_id is None:
            return {}
        return self.get_metadata(external_id, **kwargs)

    def _parent(self, item, *keys, **kwargs):
        for key in keys:
            if item.get(key):
                return self._fetch(item[key], kwargs.get('user_id'), kwargs.get('skip_cache', False))
        return {}

    def _local(self, entity, external_id):
        return self.mapper.get_or_create(entity, external_id) if external_id else ''

    def get_metadata(self, external_id, user_id=None, skip_cache=False, media_info=True,
                     media_source_id=None):
        item = self._fetch(external_id, user_id, skip_cache, media_source_id)
        media_type = map_item_type(item)
        parent = grandparent = {}
        if media_type == 'episode':
            parent = self._parent(item, 'SeasonId', user_id=user_id, skip_cache=skip_cache)
            grandparent = self._parent(item, 'SeriesId', user_id=user_id, skip_cache=skip_cache)
        elif media_type == 'track':
            parent = self._parent(item, 'AlbumId', 'ParentId', user_id=user_id, skip_cache=skip_cache)
            artist_id = item.get('AlbumArtists', [{}])[0].get('Id') if item.get('AlbumArtists') else None
            grandparent = self._fetch(artist_id, user_id, skip_cache) if artist_id else {}
        elif media_type in ('season', 'album'):
            parent = self._parent(item, 'SeriesId', 'ParentId', user_id=user_id, skip_cache=skip_cache)

        library_external = item.get('CollectionFolderId') or item.get('TopParentId')
        library_name = item.get('CollectionFolderName', '')
        if not library_external:
            for ancestor in self.client.get_ancestors(item['Id'], user_id=user_id) or []:
                if ancestor.get('Type') in ('CollectionFolder', 'UserView'):
                    library_external = ancestor.get('Id')
                    library_name = ancestor.get('Name', '')
                    break
        entity = ENTITY_COLLECTION if media_type == 'collection' else ENTITY_PLAYLIST if media_type == 'playlist' else ENTITY_ITEM
        people = item.get('People') or []
        directors = [p.get('Name', '') for p in people if p.get('Type') == 'Director']
        writers = [p.get('Name', '') for p in people if p.get('Type') == 'Writer']
        actors = [p.get('Name', '') for p in people if p.get('Type') in ('Actor', 'GuestStar')]
        provider_ids = item.get('ProviderIds') or {}
        guids = ['{}://{}'.format(PROVIDER_SCHEMES[k], v) for k, v in provider_ids.items()
                 if k in PROVIDER_SCHEMES and v]
        guid = 'jellyfin://{}/{}'.format(media_type, item['Id'])
        thumb = make_image_reference(item['Id']) if item.get('ImageTags', {}).get('Primary') else ''
        art = make_image_reference(item['Id'], 'Backdrop') if item.get('BackdropImageTags') else ''
        metadata = {
            'media_type': media_type, 'section_id': self._local(ENTITY_LIBRARY, library_external),
            'library_name': library_name,
            'rating_key': self._local(entity, item['Id']),
            'parent_rating_key': self._local(ENTITY_ITEM, parent.get('Id')),
            'grandparent_rating_key': self._local(ENTITY_ITEM, grandparent.get('Id')),
            'title': item.get('Name', ''), 'parent_title': parent.get('Name', ''),
            'grandparent_title': grandparent.get('Name', ''),
            'original_title': item.get('OriginalTitle') or item.get('Name', ''),
            'sort_title': item.get('SortName') or item.get('Name', ''),
            'media_index': item.get('IndexNumber', ''), 'parent_media_index': item.get('ParentIndexNumber', ''),
            'studio': (item.get('Studios') or [{}])[0].get('Name', ''),
            'content_rating': item.get('OfficialRating', ''), 'summary': item.get('Overview', ''),
            'tagline': (item.get('Taglines') or [''])[0], 'rating': item.get('CommunityRating', ''),
            'audience_rating': item.get('CriticRating', ''),
            'user_rating': (item.get('UserData') or {}).get('Rating', ''),
            'duration': _milliseconds(item.get('RunTimeTicks')), 'year': item.get('ProductionYear', ''),
            'thumb': thumb, 'parent_thumb': make_image_reference(parent['Id']) if parent.get('ImageTags', {}).get('Primary') else '',
            'grandparent_thumb': make_image_reference(grandparent['Id']) if grandparent.get('ImageTags', {}).get('Primary') else '',
            'art': art, 'banner': make_image_reference(item['Id'], 'Banner') if item.get('ImageTags', {}).get('Banner') else '',
            'originally_available_at': _date(item.get('PremiereDate')),
            'added_at': _epoch(item.get('DateCreated')), 'updated_at': _epoch(item.get('DateLastSaved')),
            'last_viewed_at': _epoch((item.get('UserData') or {}).get('LastPlayedDate')),
            'guid': guid, 'parent_guid': 'jellyfin://{}/{}'.format(map_item_type(parent), parent['Id']) if parent else '',
            'grandparent_guid': 'jellyfin://{}/{}'.format(map_item_type(grandparent), grandparent['Id']) if grandparent else '',
            'directors': directors, 'writers': writers, 'actors': actors,
            'genres': item.get('Genres') or [], 'labels': item.get('Tags') or [],
            'collections': [], 'guids': guids, 'markers': [],
            'full_title': ' - '.join(x for x in (grandparent.get('Name'), parent.get('Name'), item.get('Name')) if x),
            'media_info': self._media_info(item, media_source_id) if media_info else [],
            'media_backend': 'jellyfin', 'external_item_id': item['Id'],
            'external_library_id': library_external or None,
        }
        return metadata

    def _media_info(self, item, media_source_id=None):
        output = []
        for source in item.get('MediaSources') or []:
            if media_source_id and source.get('Id') != media_source_id:
                continue
            streams = []
            for stream in source.get('MediaStreams') or []:
                stream_type = {'Video': 1, 'Audio': 2, 'Subtitle': 3}.get(stream.get('Type'))
                if not stream_type: continue
                streams.append({
                    'id': stream.get('Index', ''), 'type': stream_type, 'codec': stream.get('Codec', ''),
                    'bitrate': stream.get('BitRate', ''), 'bit_depth': stream.get('BitDepth', ''),
                    'width': stream.get('Width', ''), 'height': stream.get('Height', ''),
                    'frame_rate': stream.get('AverageFrameRate', ''), 'profile': stream.get('Profile', ''),
                    'level': stream.get('Level', ''), 'channels': stream.get('Channels', ''),
                    'channel_layout': stream.get('ChannelLayout', ''), 'sampling_rate': stream.get('SampleRate', ''),
                    'language': stream.get('Language', ''), 'forced': int(bool(stream.get('IsForced'))),
                    'location': 'external' if stream.get('IsExternal') else 'embedded',
                    'color_primaries': stream.get('ColorPrimaries', ''), 'color_range': stream.get('ColorRange', ''),
                    'color_space': stream.get('ColorSpace', ''), 'color_trc': stream.get('ColorTransfer', ''),
                    'dovi_profile': stream.get('DvProfile', ''), 'dovi_level': stream.get('DvLevel', ''),
                    'dovi_bl_present': int(bool(stream.get('BlPresentFlag'))),
                    'dovi_el_present': int(bool(stream.get('ElPresentFlag'))),
                    'dovi_rpu_present': int(bool(stream.get('RpuPresentFlag'))),
                    'hdr10_plus_present': int(bool(stream.get('Hdr10PlusPresentFlag'))),
                    'dynamic_range': stream.get('VideoRangeType') or stream.get('VideoRange') or '',
                })
            part = {'id': source.get('Id', ''), 'file': source.get('Path', ''),
                    'container': source.get('Container', ''), 'duration': _milliseconds(source.get('RunTimeTicks')),
                    'streams': streams}
            output.append({'id': source.get('Id', ''), 'container': source.get('Container', ''),
                           'bitrate': source.get('Bitrate', ''), 'duration': _milliseconds(source.get('RunTimeTicks')),
                           'parts': [part]})
        return output

    def get_children(self, local_item_id, **kwargs):
        external_id = next((value for entity in (ENTITY_ITEM, ENTITY_COLLECTION, ENTITY_PLAYLIST)
                            if (value := self.mapper.to_external(entity, local_item_id)) is not None), None)
        if external_id is None: return {'children_count': 0, 'children_type': '', 'title': '', 'children_list': []}
        result = self.client.get_items(parentId=external_id, recursive=False, fields=self.FIELDS)
        children = [self.get_metadata(item['Id'], **kwargs) for item in result.get('Items', [])]
        return {'children_count': len(children), 'children_type': children[0]['media_type'] if children else '',
                'title': '', 'children_list': children}
