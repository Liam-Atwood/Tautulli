from io import BytesIO
from types import SimpleNamespace

import jsonschema
import pytest

import plexpy
from plexpy.media_backend.jellyfin.client import JellyfinImage
from plexpy.media_backend.errors import BackendConfigurationError, BackendFeatureUnsupportedError
from plexpy.media_backend.jellyfin import (
    DEFAULT_LOCAL_NETWORKS, JellyfinActivityNormalizer, JellyfinBackend, JellyfinMetadataAdapter,
    classify_endpoint, make_image_reference, map_item_type, parse_image_reference, stable_session_key,
)
from tests.test_contracts import validator


class Mapper:
    def __init__(self):
        self.ids, self.reverse, self.next = {}, {}, 1000000000000

    def get_or_create(self, entity, external):
        key = (entity, str(external))
        if key not in self.ids:
            self.ids[key] = self.next
            self.reverse[(entity, self.next)] = str(external)
            self.next += 1
        return self.ids[key]

    def to_external(self, entity, local):
        return self.reverse.get((entity, int(local)))


class Client:
    server_id = 'server-one'
    server_version = '10.11.11'

    def __init__(self, items=None, sessions=None):
        self.items = items or {}
        self.sessions = sessions or []
        self.item_calls = []
        self.session_calls = 0

    def connect(self): return {'Id': self.server_id, 'Version': self.server_version}
    def get_system_info(self):
        return {'Id': self.server_id, 'Version': self.server_version,
                'ServerName': 'Fixture Jellyfin', 'OperatingSystem': 'Linux'}
    def get_item(self, item_id, user_id=None, fields=None):
        self.item_calls.append(str(item_id))
        return self.items[str(item_id)]
    def get_items(self, **params): return {'Items': []}
    def get_sessions(self, **params):
        self.session_calls += 1
        return self.sessions


def movie_item():
    return {
        'Id': 'movie-external', 'Type': 'Movie', 'Name': 'Fixture Movie',
        'OriginalTitle': 'Original Fixture', 'SortName': 'Fixture Movie',
        'CollectionFolderId': 'library-external', 'CollectionFolderName': 'Movies',
        'RunTimeTicks': 6000000000, 'ProductionYear': 2025, 'OfficialRating': 'PG',
        'Overview': 'Summary', 'Taglines': ['Tagline'], 'Genres': ['Drama'], 'Tags': ['Fixture'],
        'Studios': [{'Name': 'Studio'}], 'People': [
            {'Name': 'Director', 'Type': 'Director'}, {'Name': 'Writer', 'Type': 'Writer'},
            {'Name': 'Actor', 'Type': 'Actor'}],
        'ProviderIds': {'Imdb': 'tt0000001', 'Tmdb': '1'},
        'ImageTags': {'Primary': 'tag'}, 'BackdropImageTags': ['tag'],
        'MediaSources': [{'Id': 'source-one', 'Name': 'Original', 'Path': '/media/movie.mkv',
            'Container': 'mkv', 'Bitrate': 8000000, 'RunTimeTicks': 6000000000,
            'MediaStreams': [
                {'Index': 0, 'Type': 'Video', 'Codec': 'hevc', 'BitRate': 7000000,
                 'BitDepth': 10, 'Width': 3840, 'Height': 2160, 'AverageFrameRate': 24,
                 'Profile': 'Main 10', 'VideoRangeType': 'DOVIWithHDR10', 'DvProfile': 8,
                 'DvLevel': 6, 'BlPresentFlag': True, 'RpuPresentFlag': True},
                {'Index': 1, 'Type': 'Audio', 'Codec': 'aac', 'Channels': 2, 'Language': 'eng'},
                {'Index': 2, 'Type': 'Subtitle', 'Codec': 'srt', 'Language': 'eng',
                 'IsExternal': True, 'IsForced': True},
            ]}],
    }


def test_type_mapping_and_strict_image_references():
    assert map_item_type({'Type': 'Audio'}) == 'track'
    assert map_item_type({'Type': 'Recording', 'SeriesId': 'series'}) == 'episode'
    assert map_item_type({'Type': 'Recording'}) == 'movie'
    with pytest.raises(BackendFeatureUnsupportedError):
        map_item_type({'Type': 'Book'})
    reference = make_image_reference('abc', 'Backdrop', 2)
    assert parse_image_reference(reference) == ('item', 'abc', 'Backdrop', 2)
    with pytest.raises(BackendConfigurationError):
        parse_image_reference('https://server/Items/abc?api_key=secret')


@pytest.mark.parametrize('jellyfin_type,expected', [
    ('Movie', 'movie'), ('Series', 'show'), ('Season', 'season'), ('Episode', 'episode'),
    ('MusicArtist', 'artist'), ('MusicAlbum', 'album'), ('Audio', 'track'),
    ('BoxSet', 'collection'), ('Playlist', 'playlist'), ('Photo', 'photo'),
    ('PhotoAlbum', 'photo_album'), ('Trailer', 'clip'), ('MusicVideo', 'clip'),
    ('Video', 'clip'), ('LiveTvProgram', 'episode'),
])
def test_all_supported_item_type_mappings(jellyfin_type, expected):
    assert map_item_type({'Type': jellyfin_type}) == expected


def test_metadata_normalizes_frozen_contract_and_caches():
    client, mapper = Client({'movie-external': movie_item()}), Mapper()
    adapter = JellyfinMetadataAdapter(client, mapper)
    metadata = adapter.get_metadata('movie-external')
    schema = __import__('json').load(open('tests/contracts/metadata.schema.json'))
    jsonschema.Draft202012Validator(schema).validate(metadata)
    assert metadata['rating_key'] >= 1000000000000
    assert metadata['duration'] == '600000'
    assert metadata['guid'] == 'jellyfin://movie/movie-external'
    assert metadata['guids'] == ['imdb://tt0000001', 'tmdb://1']
    streams = metadata['media_info'][0]['parts'][0]['streams']
    assert streams[0]['dovi_profile'] == 8 and streams[0]['dynamic_range'] == 'DOVIWithHDR10'
    assert streams[2]['location'] == 'external' and streams[2]['forced'] == 1
    adapter.get_metadata('movie-external')
    assert client.item_calls == ['movie-external']


def test_backend_rejects_server_identity_change(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        MEDIA_SERVER_URL='http://example.invalid', MEDIA_SERVER_TOKEN='token',
        MEDIA_SERVER_VERIFY_TLS=True, MEDIA_SERVER_ID='different', PMS_TIMEOUT=15))
    backend = JellyfinBackend(client=Client(), url='http://example.invalid', token='token',
                              server_id='different')
    with pytest.raises(BackendConfigurationError, match='identity'):
        backend.get_server_info()


def test_activity_normalizes_without_side_effects():
    item, mapper = movie_item(), Mapper()
    raw = {'Id': 'session-one', 'UserId': 'user-one', 'UserName': 'Admin',
           'DeviceId': 'device-one', 'DeviceName': 'Browser', 'DeviceType': 'Chrome',
           'Client': 'Jellyfin Web', 'ApplicationVersion': '1', 'RemoteEndPoint': '192.168.1.2:5000',
           'NowPlayingItem': item, 'PlayState': {'PositionTicks': 1200000000, 'IsPaused': True,
               'PlayMethod': 'Transcode', 'MediaSourceId': 'source-one', 'AudioStreamIndex': 1,
               'SubtitleStreamIndex': 2},
           'TranscodingInfo': {'Container': 'ts', 'Protocol': 'hls', 'VideoCodec': 'h264',
               'AudioCodec': 'aac', 'AudioChannels': 2, 'Width': 1920, 'Height': 1080,
               'Bitrate': 4000000, 'HardwareAccelerationType': 'vaapi'}}
    client = Client({'movie-external': item}, [raw])
    adapter = JellyfinMetadataAdapter(client, mapper)
    result = JellyfinActivityNormalizer(client, mapper, adapter).get_current_activity()
    validator('current_activity.schema.json').validate(result)
    session = result['sessions'][0]
    assert result['stream_count'] == '1'
    assert result['stream_count_transcode'] == 1 and result['total_bandwidth'] == 4000
    assert result['lan_bandwidth'] == 4000 and result['wan_bandwidth'] == 0
    assert session['state'] == 'paused' and session['view_offset'] == '120000'
    assert session['transcode_decision'] == 'transcode'
    assert session['location'] == 'lan' and session['secure'] is None and session['relayed'] == 0
    assert session['external_session_id'] == 'session-one'
    assert set(__import__('json').load(open('tests/fixtures/normalized/session_base.json'))) <= set(session)


def test_activity_cache_bypass_and_malformed_session_tolerance():
    item, mapper = movie_item(), Mapper()
    valid = {'Id': 'session', 'UserId': 'user', 'DeviceId': 'device',
             'RemoteEndPoint': '[2001:db8::1]:9000', 'NowPlayingItem': item,
             'PlayState': {'PlayMethod': 'DirectPlay'}}
    client = Client({'movie-external': item}, [{'Id': 'empty'}, valid])
    normalizer = JellyfinActivityNormalizer(client, mapper, JellyfinMetadataAdapter(client, mapper))
    first = normalizer.get_current_activity()
    second = normalizer.get_current_activity()
    refreshed = normalizer.get_current_activity(skip_cache=True)
    assert first == second == refreshed
    assert client.session_calls == 2
    assert first['stream_count_direct_play'] == 1 and first['wan_bandwidth'] == 8000
    assert first['sessions'][0]['secure'] is None


def test_network_and_session_keys_are_stable():
    assert classify_endpoint('[fd00::1]:8096')[1:] == (1, 'lan')
    assert classify_endpoint('203.0.113.2:80')[1:] == (0, 'wan')
    assert stable_session_key('server', 'session') == stable_session_key('server', 'session')
    original = stable_session_key('server', 'session')
    used = {original}
    assert stable_session_key('server', 'session', used) != original


def test_backend_transforms_images_without_exposing_token(monkeypatch):
    pil = pytest.importorskip('PIL.Image')
    source = BytesIO()
    pil.new('RGB', (20, 10), '#ff0000').save(source, 'PNG')

    client = Client()
    client.get_image = lambda *args, **kwargs: JellyfinImage(source.getvalue(), 'image/png', 'old')
    backend = JellyfinBackend(client=client, url='http://example.invalid', token='secret')
    result = backend.get_image(
        'jellyfin://item/movie-external/Primary/0', width=8, height=8, clip=True,
        opacity=75, background='#000000', blur=5, img_format='jpeg')
    assert result.content_type == 'image/jpeg'
    assert result.etag.startswith('"') and 'secret' not in result.etag
    with pil.open(BytesIO(result.data)) as transformed:
        assert transformed.size == (8, 8)


def test_backend_rejects_corrupt_image_transform():
    client = Client()
    client.get_image = lambda *args, **kwargs: JellyfinImage(b'not-an-image', 'image/png', None)
    backend = JellyfinBackend(client=client, url='http://example.invalid', token='secret')
    with pytest.raises(Exception, match='transform'):
        backend.get_image('jellyfin://item/movie-external/Primary/0', width=8)
