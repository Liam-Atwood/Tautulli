import concurrent.futures
import multiprocessing
import sqlite3
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import plexpy
from plexpy import database
from plexpy.media_backend import (
    ENTITY_ITEM, ENTITY_LIBRARY, ENTITY_USER, ExternalIdMapper, IdentityMappingError,
    IdentityMappingExhaustedError,
)


def configure_database(path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(path.parent))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(path))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        BACKUP_DIR=str(path.parent / 'backups'), BACKUP_DAYS=3,
    ))


def create_database(path, monkeypatch):
    configure_database(path, monkeypatch)
    plexpy.dbcheck()
    return path


def process_allocate(arguments):
    path, external_id = arguments
    return ExternalIdMapper('jellyfin', 'server-a', path).get_or_create(ENTITY_ITEM, external_id)


def test_clean_database_schema_and_idempotence(tmp_path, monkeypatch):
    path = create_database(tmp_path / 'clean.db', monkeypatch)
    connection = sqlite3.connect(path)
    columns = {row[1]: row for row in connection.execute('PRAGMA table_info(session_history)')}
    assert columns['media_backend'][3] == 1
    assert columns['media_backend'][4] == "'plex'"
    assert {'external_item_id', 'external_user_id', 'external_library_id', 'external_session_id'} <= set(columns)
    version = connection.execute(
        "SELECT value FROM version_info WHERE key = ?", [database.MEDIA_BACKEND_SCHEMA_KEY]
    ).fetchone()[0]
    indexes = {row[1] for row in connection.execute('PRAGMA index_list(external_id_map)')}
    connection.close()
    assert version == '2'
    history_indexes = {row[1] for row in sqlite3.connect(path).execute(
        'PRAGMA index_list(session_history)')}
    assert 'idx_session_history_jellyfin_identity' in history_indexes
    assert {'idx_external_id_map_external', 'idx_external_id_map_local'} <= indexes
    assert database.migrate_media_backend_schema(path, backup_required=False) is False
    assert not (tmp_path / 'backups').exists()


def test_populated_legacy_upgrade_backs_up_and_preserves_rows(tmp_path):
    path = tmp_path / 'legacy.db'
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE version_info (key TEXT UNIQUE, value TEXT);"
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY, rating_key INTEGER, user_id INTEGER, section_id INTEGER);"
        "CREATE TABLE session_history (id INTEGER PRIMARY KEY, rating_key INTEGER, user_id INTEGER, section_id INTEGER);"
        "INSERT INTO session_history VALUES (1, 42, 7, 3);"
    )
    connection.commit()
    connection.close()
    events = []
    assert database.migrate_media_backend_schema(
        path, backup_required=True, backup_callback=lambda: events.append('backup') or True,
        before_commit=lambda connection: events.append('ddl'))
    connection = sqlite3.connect(path)
    assert connection.execute(
        'SELECT rating_key, user_id, section_id, media_backend FROM session_history'
    ).fetchone() == (42, 7, 3, 'plex')
    connection.close()
    assert events == ['backup', 'ddl']


def test_populated_upgrade_backup_contains_pre_migration_schema(tmp_path, monkeypatch):
    path = tmp_path / 'tautulli.db'
    connection = sqlite3.connect(path)
    connection.executescript(
        'CREATE TABLE version_info (key TEXT UNIQUE, value TEXT);'
        'CREATE TABLE sessions (id INTEGER PRIMARY KEY);'
        'CREATE TABLE session_history (id INTEGER PRIMARY KEY);'
    )
    connection.commit()
    connection.close()
    configure_database(path, monkeypatch)
    assert database.migrate_media_backend_schema(path, backup_required=True)
    archives = list((tmp_path / 'backups').glob('*.zip'))
    assert len(archives) == 1
    restored = tmp_path / 'restored'
    with zipfile.ZipFile(archives[0]) as archive:
        archive.extract(database.FILENAME, restored)
    connection = sqlite3.connect(restored / database.FILENAME)
    assert not database._table_exists(connection, 'external_id_map')
    assert 'media_backend' not in database._table_columns(connection, 'session_history')
    connection.close()


def test_backup_and_migration_failures_leave_legacy_schema_untouched(tmp_path):
    for name, backup, hook in (
            ('backup.db', lambda: False, None),
            ('rollback.db', lambda: True, lambda connection: (_ for _ in ()).throw(RuntimeError('injected')))):
        path = tmp_path / name
        connection = sqlite3.connect(path)
        connection.executescript(
            'CREATE TABLE version_info (key TEXT UNIQUE, value TEXT);'
            'CREATE TABLE sessions (id INTEGER PRIMARY KEY);'
            'CREATE TABLE session_history (id INTEGER PRIMARY KEY);'
        )
        connection.commit()
        connection.close()
        with pytest.raises(RuntimeError):
            database.migrate_media_backend_schema(
                path, backup_required=True, backup_callback=backup, before_commit=hook)
        connection = sqlite3.connect(path)
        assert not database._table_exists(connection, 'external_id_map')
        assert 'media_backend' not in database._table_columns(connection, 'session_history')
        connection.close()


def test_mapper_namespaces_reverse_lookup_and_stability(tmp_path, monkeypatch):
    path = create_database(tmp_path / 'map.db', monkeypatch)
    mapper = ExternalIdMapper('JELLYFIN', 'Server-A', path)
    item = mapper.get_or_create(ENTITY_ITEM, 'Item-A')
    assert item == database.EXTERNAL_ID_FLOOR
    assert mapper.get_or_create(ENTITY_ITEM, 'Item-A') == item
    assert mapper.to_local(ENTITY_ITEM, 'Item-A') == item
    assert mapper.to_external(ENTITY_ITEM, item) == 'Item-A'
    assert mapper.to_local(ENTITY_ITEM, 'item-a') is None
    assert mapper.to_external(ENTITY_ITEM, item + 999) is None
    values = {
        item,
        mapper.get_or_create(ENTITY_USER, 'Item-A'),
        mapper.get_or_create(ENTITY_ITEM, 'Item-B'),
        ExternalIdMapper('jellyfin', 'Server-B', path).get_or_create(ENTITY_ITEM, 'Item-A'),
        ExternalIdMapper('other', 'Server-A', path).get_or_create(ENTITY_ITEM, 'Item-A'),
    }
    assert len(values) == 5
    user = mapper.get_or_create(ENTITY_USER, 'User-A')
    connection = sqlite3.connect(path)
    connection.execute('INSERT INTO users (user_id, username) VALUES (?, ?)', [user, 'temporary'])
    connection.execute('DELETE FROM users WHERE user_id = ?', [user])
    connection.commit()
    connection.close()
    assert mapper.get_or_create(ENTITY_ITEM, 'Item-A') == item
    assert mapper.get_or_create(ENTITY_USER, 'User-A') == user


@pytest.mark.parametrize('arguments', [('', 'server', ENTITY_ITEM, 'id'), ('jellyfin', '', ENTITY_ITEM, 'id'),
                                        ('jellyfin', 'server', 'invalid', 'id'), ('jellyfin', 'server', ENTITY_ITEM, '')])
def test_mapper_rejects_invalid_identities(tmp_path, monkeypatch, arguments):
    path = create_database(tmp_path / 'invalid.db', monkeypatch)
    backend, server, entity, external = arguments
    with pytest.raises(IdentityMappingError):
        ExternalIdMapper(backend, server, path).get_or_create(entity, external)


def test_counter_seeds_above_legacy_ids_and_detects_exhaustion(tmp_path, monkeypatch):
    path = create_database(tmp_path / 'counter.db', monkeypatch)
    connection = sqlite3.connect(path)
    legacy_id = database.EXTERNAL_ID_FLOOR + 100
    connection.execute('INSERT INTO users (user_id, username) VALUES (?, ?)', [legacy_id, 'legacy'])
    database.reseed_external_id_counter(connection=connection)
    connection.commit()
    connection.close()
    mapper = ExternalIdMapper('jellyfin', 'server', path)
    assert mapper.get_or_create(ENTITY_USER, 'new') == legacy_id + 1
    connection = sqlite3.connect(path)
    connection.execute(
        'UPDATE version_info SET value = ? WHERE key = ?',
        [str(database.MAX_SAFE_INTEGER + 1), database.EXTERNAL_ID_COUNTER_KEY])
    connection.commit()
    connection.close()
    with pytest.raises(IdentityMappingExhaustedError):
        mapper.get_or_create(ENTITY_LIBRARY, 'too-late')


def test_mapper_rolls_back_counter_when_insert_fails(tmp_path, monkeypatch):
    path = create_database(tmp_path / 'rollback-map.db', monkeypatch)
    connection = sqlite3.connect(path)
    original_counter = connection.execute(
        'SELECT value FROM version_info WHERE key = ?', [database.EXTERNAL_ID_COUNTER_KEY]
    ).fetchone()[0]
    connection.execute(
        "CREATE TRIGGER reject_mapping BEFORE INSERT ON external_id_map "
        "BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    connection.commit()
    connection.close()
    mapper = ExternalIdMapper('jellyfin', 'server', path)
    with pytest.raises(IdentityMappingError):
        mapper.get_or_create(ENTITY_ITEM, 'failure')
    connection = sqlite3.connect(path)
    assert connection.execute('SELECT COUNT(*) FROM external_id_map').fetchone()[0] == 0
    assert connection.execute(
        'SELECT value FROM version_info WHERE key = ?', [database.EXTERNAL_ID_COUNTER_KEY]
    ).fetchone()[0] == original_counter
    connection.close()


def test_concurrent_threads_and_processes_allocate_once(tmp_path, monkeypatch):
    path = create_database(tmp_path / 'concurrent.db', monkeypatch)
    mapper = ExternalIdMapper('jellyfin', 'server-a', path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        thread_ids = list(executor.map(lambda _: mapper.get_or_create(ENTITY_ITEM, 'shared'), range(32)))
    assert len(set(thread_ids)) == 1
    context = multiprocessing.get_context('spawn')
    with context.Pool(4) as pool:
        process_ids = pool.map(process_allocate, [(str(path), 'process-shared')] * 12)
    assert len(set(process_ids)) == 1
    connection = sqlite3.connect(path)
    assert connection.execute('SELECT COUNT(*) FROM external_id_map').fetchone()[0] == 2
    connection.close()
