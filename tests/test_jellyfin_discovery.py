from types import SimpleNamespace

import plexpy
from plexpy import libraries
from plexpy.media_backend.jellyfin.backend import JellyfinBackend


class Client:
    server_id = 'server-a'
    server_version = '10.11.11'

    def search_items(self, query, **kwargs):
        self.search = (query, kwargs)
        return {'Items': [{'Id': 'movie'}, {'Id': 'album'}, {'Id': 'box'}]}

    def get_collections(self, **kwargs):
        self.collections = kwargs
        return {'Items': [{'Id': 'box', 'ChildCount': 2}]}

    def get_playlists(self, **kwargs):
        self.playlists = kwargs
        return {'Items': [{'Id': 'playlist', 'ChildCount': 3}]}


class Mapper:
    def get_or_create(self, entity, external):
        return {'movie': 11, 'album': 12, 'box': 13, 'playlist': 14}.get(external, 15)

    def to_external(self, entity, local):
        return 'library' if str(local) == '7' else None


class Metadata:
    def get_metadata(self, external, **kwargs):
        media_type = {'movie': 'movie', 'album': 'album', 'box': 'collection',
                      'playlist': 'playlist'}[external]
        return {'media_type': media_type, 'rating_key': 1, 'external_item_id': external,
                'title': external.title(), 'sort_title': external.title(), 'section_id': 7,
                'library_name': 'Visible', 'added_at': '100', 'updated_at': '101',
                'summary': '', 'guid': 'jellyfin://{}/{}'.format(media_type, external),
                'thumb': 'jellyfin://item/{}/Primary/0'.format(external), 'art': '',
                'duration': '10', 'media_info': []}


def backend(monkeypatch):
    value = object.__new__(JellyfinBackend)
    value.client, value._mapper, value._metadata = Client(), Mapper(), Metadata()
    value._configured_server_id = ''
    monkeypatch.setattr(value, '_ensure_connected', lambda: None)
    return value


def test_search_groups_normalized_media_and_preserves_shape(monkeypatch):
    value = backend(monkeypatch)
    result = value.get_search_results('term', limit='8', user_id='user')
    assert result['results_count'] == 3
    assert [item['external_item_id'] for item in result['results_list']['movie']] == ['movie']
    assert [item['external_item_id'] for item in result['results_list']['album']] == ['album']
    assert [item['external_item_id'] for item in result['results_list']['collection']] == ['box']
    assert value.client.search[1]['user_id'] == 'user'


def test_collections_and_playlists_use_authorized_scope(monkeypatch):
    value = backend(monkeypatch)
    collection = value.get_collections(section_id=7, user_id='guest')[0]
    playlist = value.get_playlists(section_id=7, user_id='guest')[0]
    assert collection['rating_key'] == 13 and collection['child_count'] == 2
    assert playlist['rating_key'] == 14 and playlist['child_count'] == 3
    assert value.client.collections == {'parent_id': 'library', 'user_id': 'guest', 'limit': 100}
    assert value.client.playlists == {'user_id': 'guest', 'limit': 100}


def test_library_helpers_do_not_construct_plex_server_for_jellyfin(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(MEDIA_SERVER_TYPE='jellyfin'))
    value = backend(monkeypatch)
    monkeypatch.setattr('plexpy.media_backend.factory.get_media_backend', lambda name: value)
    monkeypatch.setattr(libraries, 'Plex', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    assert libraries.get_collections(7)[0]['ratingKey'] == 13
    assert libraries.get_playlists(7, 'guest')[0]['ratingKey'] == 14
