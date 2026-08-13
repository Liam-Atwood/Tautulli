import sqlite3
from types import SimpleNamespace

import plexpy
from plexpy import datafactory, database
from plexpy.media_backend.jellyfin.backend import JellyfinBackend


class RecentClient:
    server_id = 'server-a'
    server_version = '10.11.11'

    def get_latest_items(self, **params):
        self.params = params
        return {'Items': [{'Id': 'newer'}, {'Id': 'older'}], 'TotalRecordCount': 2}


class Metadata:
    def get_metadata(self, external_id):
        return {
            'rating_key': 1000000000001 if external_id == 'newer' else 1000000000002,
            'parent_rating_key': '', 'grandparent_rating_key': '', 'section_id': 1000000000003,
            'media_type': 'movie', 'media_info': [], 'added_at': '200' if external_id == 'newer' else '100',
            'external_item_id': external_id, 'media_backend': 'jellyfin', 'full_title': external_id,
        }


def test_recently_added_contract_pagination_and_order(monkeypatch):
    client = RecentClient()
    backend = object.__new__(JellyfinBackend)
    backend.client, backend._metadata = client, Metadata()
    backend._configured_server_id = ''
    backend._mapper = None
    monkeypatch.setattr(backend, '_ensure_connected', lambda: None)
    output = backend.get_recently_added_details(start='3', count='2', media_type='movie')
    assert [item['external_item_id'] for item in output['recently_added']] == ['newer', 'older']
    assert client.params['start'] == 3 and client.params['limit'] == 2
    assert client.params['include_item_types'] == ('Movie',)


def test_recently_added_generation_is_restart_safe(tmp_path, monkeypatch):
    path = tmp_path / 'tautulli.db'
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(path))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        BACKUP_DIR=str(tmp_path / 'backups'), BACKUP_DAYS=3))
    plexpy.dbcheck()
    metadata = Metadata().get_metadata('newer')
    metadata['server_id'] = 'server-a'
    factory = datafactory.DataFactory()
    assert factory.set_recently_added_item(metadata=metadata) is True
    metadata['full_title'] = 'metadata edit'
    assert factory.set_recently_added_item(metadata=metadata) is False
    metadata['added_at'] = '201'
    assert factory.set_recently_added_item(metadata=metadata) is True
    connection = sqlite3.connect(path)
    assert connection.execute(
        "SELECT COUNT(*) FROM recently_added WHERE media_backend='jellyfin'"
    ).fetchone()[0] == 2
    columns = {row[1] for row in connection.execute('PRAGMA table_info(recently_added)')}
    assert {'media_backend', 'server_id', 'external_item_id', 'addition_generation'} <= columns
    assert connection.execute(
        "SELECT value FROM version_info WHERE key=?", [database.MEDIA_BACKEND_SCHEMA_KEY]
    ).fetchone()[0] == '3'
    connection.close()
