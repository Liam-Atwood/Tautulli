from io import BytesIO
import json
from types import SimpleNamespace

import jsonschema
import pytest

import plexpy
from plexpy.media_backend.errors import BackendConfigurationError, BackendFeatureUnsupportedError
from plexpy.media_backend.jellyfin import (
    JellyfinBackend, JellyfinMetadataAdapter, make_image_reference, map_item_type,
    parse_image_reference,
)
from plexpy.media_backend.jellyfin.client import JellyfinImage

class Mapper:
    def __init__(self):
        self.ids, self.reverse, self.next = {}, {}, 1000000000000

    def get_or_create(self, entity, external):
        key = entity, str(external)
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

    def __init__(self, items=None):
        self.items = items or {}
        self.item_calls = []

    def connect(self):
        return {'Id': self.server_id, 'Version': self.server_version}

    def get_system_info(self):
        return {'Id': self.server_id, 'Version': self.server_version,
                'ServerName': 'Fixture Jellyfin', 'OperatingSystem': 'Linux'}

    def get_item(self, item_id, user_id=None, fields=None):
        self.item_calls.append(str(item_id))
        return self.items[str(item_id)]

    def get_items(self, **params):
        return {'Items': []}

    def get_ancestors(self, item_id, user_id=None):
        return []


def movie_item():
    return {
        'Id': 'movie-external', 'Type': 'Movie', 'Name': 'Fixture Movie',
        'CollectionFolderId': 'library-external', 'RunTimeTicks': 6000000000,
        'ProviderIds': {'Imdb': 'tt0000001', 'Tmdb': '1'},
        'ImageTags': {'Primary': 'tag'}, 'BackdropImageTags': ['tag'],
        'MediaSources': [{'Id': 'source-one', 'Container': 'mkv', 'Bitrate': 8000000,
            'RunTimeTicks': 6000000000, 'MediaStreams': [
                {'Index': 0, 'Type': 'Video', 'Codec': 'hevc', 'BitRate': 7000000,
                 'Width': 3840, 'Height': 2160, 'VideoRangeType': 'DOVIWithHDR10',
                 'DvProfile': 8, 'DvLevel': 6, 'BlPresentFlag': True,
                 'RpuPresentFlag': True},
                {'Index': 1, 'Type': 'Audio', 'Codec': 'aac', 'Channels': 2},
                {'Index': 2, 'Type': 'Subtitle', 'Codec': 'srt', 'IsExternal': True,
                 'IsForced': True},
            ]}],
    }


def test_type_mapping_and_strict_image_references():
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
    schema = json.load(open('tests/contracts/metadata.schema.json'))
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


def test_backend_transforms_images_without_exposing_token():
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
