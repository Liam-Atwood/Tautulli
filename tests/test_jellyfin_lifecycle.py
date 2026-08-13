import copy
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import plexpy
from plexpy import activity_processor, helpers


FIXTURES = Path(__file__).parent / 'fixtures' / 'normalized'


def configure(tmp_path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(tmp_path / 'tautulli.db'))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        BACKUP_DIR=str(tmp_path / 'backups'), BACKUP_DAYS=3,
        MEDIA_SERVER_ID='server-a', LOGGING_IGNORE_INTERVAL=0,
        NOTIFY_CONTINUED_SESSION_THRESHOLD=300,
    ))
    plexpy.dbcheck()


def jellyfin_session():
    session = json.loads((FIXTURES / 'session_base.json').read_text(encoding='utf-8'))
    session.update({
        'session_key': '99001', 'session_id': 'session-a',
        'media_backend': 'jellyfin', 'external_item_id': 'item-a',
        'external_user_id': 'user-a', 'external_library_id': 'library-a',
        'external_session_id': 'session-a', 'rating_key': '1000000000001',
        'user_id': '1000000000002', 'section_id': '1000000000003',
        'username': 'Ada', 'user': 'Ada', 'friendly_name': 'Ada',
        'library_name': 'Movies', 'started': 1704067200, 'stopped': 1704067800,
        'paused_counter': 0, 'product_version': '1', 'profile': '',
        'video_bit_depth': '8', 'video_codec_level': '', 'video_scan_type': 'progressive',
        'audio_language': 'English', 'audio_language_code': 'eng', 'subtitle_codec': '',
        'subtitle_forced': 0, 'subtitle_language': '', 'transcode_hw_requested': 0,
        'transcode_hw_full_pipeline': 0, 'transcode_hw_decode': '',
        'transcode_hw_decode_title': '', 'transcode_hw_encode': '',
        'transcode_hw_encode_title': '', 'stream_video_codec_level': '',
        'stream_video_bit_depth': '8', 'stream_video_scan_type': 'progressive',
        'stream_video_full_resolution': '1080p', 'stream_audio_language_code': 'eng',
        'stream_subtitle_container': '', 'stream_subtitle_forced': 0, 'subtitles': 0,
        'synced_version': 0, 'synced_version_profile': '', 'optimized_version': 0,
        'optimized_version_profile': '', 'optimized_version_title': '', 'live': 0,
        'secure': None, 'relayed': 0,
    })
    return session


def metadata():
    value = json.loads((FIXTURES / 'metadata_movie.json').read_text(encoding='utf-8'))
    value['section_id'] = '1000000000003'
    value['markers'] = []
    return value


def test_lifecycle_bootstraps_dependencies_and_assigns_stable_identity(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    monkeypatch.setattr(helpers, 'timestamp', lambda: 1704067200)
    processor = activity_processor.ActivityProcessor()
    session = jellyfin_session()
    assert processor.write_session(session, notify=False) is True
    persisted = processor.get_session_by_key(session['session_key'])
    assert len(persisted['history_identity']) == 64
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute(
        'SELECT username, keep_history FROM users WHERE user_id = ?', [session['user_id']]
    ).fetchone() == ('Ada', 1)
    assert connection.execute(
        'SELECT section_name, section_type, keep_history FROM library_sections'
    ).fetchone() == ('Movies', 'movie', 1)
    connection.close()


def test_history_bundle_is_exactly_once(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    processor = activity_processor.ActivityProcessor()
    session = jellyfin_session()
    session['history_identity'] = processor._history_identity(session, session['started'])
    for _ in range(2):
        processor.write_session_history(
            session=copy.deepcopy(session), import_metadata=metadata(), is_import=True)
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute('SELECT COUNT(*) FROM session_history').fetchone()[0] == 1
    assert connection.execute('SELECT COUNT(*) FROM session_history_media_info').fetchone()[0] == 1
    assert connection.execute('SELECT COUNT(*) FROM session_history_metadata').fetchone()[0] == 1
    connection.close()


def test_elapsed_pause_accounting_uses_timestamps(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    processor = activity_processor.ActivityProcessor()
    session = jellyfin_session()
    monkeypatch.setattr(helpers, 'timestamp', lambda: 100)
    processor.write_session(session, notify=False)
    processor.set_session_last_paused(session['session_key'], 100)
    monkeypatch.setattr(helpers, 'timestamp', lambda: 137)
    processor.set_session_last_paused(session['session_key'], None)
    persisted = processor.get_session_by_key(session['session_key'])
    assert persisted['paused_counter'] == 37
    assert persisted['last_paused'] is None


def test_failed_history_bundle_rolls_back_all_rows(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    session = jellyfin_session()
    history = {'started': session['started'], 'stopped': session['stopped'],
               'media_backend': 'jellyfin', 'history_identity': 'atomic'}
    try:
        plexpy.database.write_session_history_bundle(
            history, {'not_a_column': 'failure'}, {'rating_key': session['rating_key']})
    except sqlite3.OperationalError:
        pass
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute('SELECT COUNT(*) FROM session_history').fetchone()[0] == 0
    connection.close()
