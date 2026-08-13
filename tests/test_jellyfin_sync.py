import sqlite3
from types import SimpleNamespace

import plexpy
from plexpy import libraries, users
from plexpy.media_backend.jellyfin.backend import JellyfinBackend


class Mapper:
    def __init__(self):
        self.values = {}

    def get_or_create(self, entity, external):
        key = (entity, external)
        if key not in self.values:
            self.values[key] = 1000000000000 + len(self.values)
        return self.values[key]


class Client:
    server_id = 'server-a'
    server_version = '10.11.11'

    def connect(self): return {}
    def get_libraries(self):
        return [{'ItemId': 'movies', 'Name': 'Movies', 'CollectionType': 'movies'},
                {'ItemId': 'shows', 'Name': 'TV', 'CollectionType': 'tvshows'}]
    def get_library_count(self, library_id, item_type=None):
        return {('movies', 'Movie'): 4, ('shows', 'Series'): 2,
                ('shows', 'Season'): 5, ('shows', 'Episode'): 20}.get((library_id, item_type), 0)
    def get_users(self):
        return [{'Id': 'admin', 'Name': 'Ada', 'PrimaryImageTag': 'tag', 'Policy': {
            'IsAdministrator': True, 'EnableAllFolders': True,
            'EnableContentDownloading': True}}, {'Id': 'guest', 'Name': 'Grace', 'Policy': {
            'EnabledFolders': ['shows'], 'EnableAllFolders': False, 'IsDisabled': True}}]


def backend():
    value = JellyfinBackend(url='http://example.invalid', token='token', client=Client(),
                            server_id='server-a')
    value._mapper = Mapper()
    return value


def configure(tmp_path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(tmp_path / 'tautulli.db'))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        BACKUP_DIR=str(tmp_path / 'backups'), BACKUP_DAYS=3,
        MEDIA_SERVER_TYPE='jellyfin', MEDIA_SERVER_ID='server-a',
        HOME_LIBRARY_CARDS=[], write=lambda: True,
    ))
    plexpy.dbcheck()


def test_backend_normalizes_library_counts_and_user_policies(monkeypatch):
    value = backend()
    normalized = value.get_libraries()
    assert [(row['section_type'], row['count'], row['parent_count'], row['child_count'])
            for row in normalized] == [('movie', 4, None, None), ('show', 2, 5, 20)]
    mapped = value.get_users()
    assert mapped[0]['is_admin'] == 1 and len(mapped[0]['shared_libraries']) == 2
    assert mapped[1]['is_active'] == 0 and len(mapped[1]['shared_libraries']) == 1


def test_authoritative_sync_is_transactional_and_preserves_preferences(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    value = backend()
    monkeypatch.setattr('plexpy.media_backend.factory.get_media_backend', lambda *args, **kwargs: value)
    assert libraries.refresh_libraries()
    assert users.refresh_users()
    connection = sqlite3.connect(plexpy.DB_FILE)
    user_id = value._mapper.values[('user', 'admin')]
    section_id = value._mapper.values[('library', 'movies')]
    connection.execute('UPDATE users SET do_notify=0, keep_history=0, custom_avatar_url=? WHERE user_id=?',
                       ['custom-user', user_id])
    connection.execute('UPDATE library_sections SET do_notify=0, keep_history=0, custom_thumb_url=? '
                       'WHERE section_id=?', ['custom-library', section_id])
    connection.commit()
    connection.close()
    assert libraries.refresh_libraries()
    assert users.refresh_users()
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute(
        'SELECT do_notify, keep_history, custom_avatar_url FROM users WHERE user_id=?', [user_id]
    ).fetchone() == (0, 0, 'custom-user')
    assert connection.execute(
        'SELECT do_notify, keep_history, custom_thumb_url FROM library_sections WHERE section_id=?',
        [section_id]).fetchone() == (0, 0, 'custom-library')
    connection.close()


def test_fetch_failure_does_not_mutate_existing_rows(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    connection = sqlite3.connect(plexpy.DB_FILE)
    connection.execute('INSERT INTO users (user_id, username) VALUES (42, ?)', ['Existing'])
    connection.commit()
    connection.close()

    class Broken:
        def get_users(self): raise RuntimeError('offline')

    monkeypatch.setattr('plexpy.media_backend.factory.get_media_backend', lambda *args, **kwargs: Broken())
    assert users.refresh_users() is False
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute('SELECT username FROM users WHERE user_id=42').fetchone()[0] == 'Existing'
    connection.close()
