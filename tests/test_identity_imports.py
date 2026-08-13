import sqlite3
from pathlib import Path
from types import SimpleNamespace

import plexpy
from plexpy import database
from plexpy.media_backend import ENTITY_ITEM, ExternalIdMapper


def configure(path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(path.parent))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(path))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        BACKUP_DIR=str(path.parent / 'backups'), BACKUP_DAYS=3,
    ))


def create_current(path, monkeypatch):
    path.parent.mkdir(parents=True, exist_ok=True)
    configure(path, monkeypatch)
    plexpy.dbcheck()
    return path


def seed_history(path, row_id, rating_key):
    connection = sqlite3.connect(path)
    connection.execute(
        'INSERT INTO session_history (id, reference_id, started, stopped, rating_key, user_id, user, '
        'media_type, section_id, view_offset) VALUES (?, ?, 1, 2, ?, 1, ?, ?, 1, 1)',
        [row_id, row_id, rating_key, 'fixture', 'movie'])
    connection.execute(
        'INSERT INTO session_history_metadata (id, rating_key, title, full_title, media_type) '
        'VALUES (?, ?, ?, ?, ?)',
        [row_id, rating_key, 'Fixture', 'Fixture', 'movie'])
    connection.execute(
        'INSERT INTO session_history_media_info (id, rating_key) VALUES (?, ?)',
        [row_id, rating_key])
    connection.commit()
    connection.close()


def test_legacy_merge_adds_defaults_and_reseeds(tmp_path, monkeypatch):
    target = create_current(tmp_path / 'target' / 'tautulli.db', monkeypatch)
    seed_history(target, 1, 10)
    source = create_current(tmp_path / 'source' / 'tautulli.db', monkeypatch)
    seed_history(source, 1, database.EXTERNAL_ID_FLOOR + 50)
    connection = sqlite3.connect(source)
    connection.execute('DROP TABLE external_id_map')
    connection.execute('DROP INDEX idx_session_history_jellyfin_identity')
    for column in ('media_backend', 'external_item_id', 'external_user_id',
                   'external_library_id', 'external_session_id'):
        connection.execute('ALTER TABLE session_history DROP COLUMN {}'.format(column))
    connection.execute('DELETE FROM version_info WHERE key IN (?, ?)', [
        database.MEDIA_BACKEND_SCHEMA_KEY, database.EXTERNAL_ID_COUNTER_KEY])
    connection.commit()
    connection.close()
    configure(target, monkeypatch)
    database.import_tautulli_db(database=str(source), method='merge', backup=False)
    connection = sqlite3.connect(target)
    rows = connection.execute(
        'SELECT rating_key, media_backend FROM session_history ORDER BY rating_key'
    ).fetchall()
    counter = int(connection.execute(
        'SELECT value FROM version_info WHERE key = ?', [database.EXTERNAL_ID_COUNTER_KEY]
    ).fetchone()[0])
    connection.close()
    assert rows == [(10, 'plex'), (database.EXTERNAL_ID_FLOOR + 50, 'plex')]
    assert counter == database.EXTERNAL_ID_FLOOR + 51
    assert not source.exists()


def test_mapped_overwrite_preserves_mapping_and_reseeds(tmp_path, monkeypatch):
    target = create_current(tmp_path / 'target' / 'tautulli.db', monkeypatch)
    ExternalIdMapper('jellyfin', 'target-server', target).get_or_create(ENTITY_ITEM, 'target-item')
    source = create_current(tmp_path / 'source' / 'tautulli.db', monkeypatch)
    source_mapper = ExternalIdMapper('jellyfin', 'source-server', source)
    source_id = source_mapper.get_or_create(ENTITY_ITEM, 'source-item')
    configure(target, monkeypatch)
    database.import_tautulli_db(database=str(source), method='overwrite', backup=False)
    connection = sqlite3.connect(target)
    mappings = connection.execute(
        'SELECT server_id, external_id, local_id FROM external_id_map'
    ).fetchall()
    counter = int(connection.execute(
        'SELECT value FROM version_info WHERE key = ?', [database.EXTERNAL_ID_COUNTER_KEY]
    ).fetchone()[0])
    connection.close()
    assert mappings == [('source-server', 'source-item', source_id)]
    assert counter == source_id + 1


def test_mapped_merge_rejects_before_backup_or_mutation(tmp_path, monkeypatch):
    target = create_current(tmp_path / 'target' / 'tautulli.db', monkeypatch)
    seed_history(target, 1, 10)
    source = create_current(tmp_path / 'source' / 'tautulli.db', monkeypatch)
    ExternalIdMapper('jellyfin', 'source-server', source).get_or_create(ENTITY_ITEM, 'source-item')
    seed_history(source, 1, 20)
    configure(target, monkeypatch)
    backup_calls = []
    monkeypatch.setattr(database, 'make_backup', lambda *args, **kwargs: backup_calls.append(True) or True)
    assert database.import_tautulli_db(
        database=str(source), method='merge', backup=True) is False
    connection = sqlite3.connect(target)
    assert connection.execute('SELECT rating_key FROM session_history').fetchall() == [(10,)]
    connection.close()
    assert backup_calls == []
    assert source.exists()
