import copy
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import plexpy
from plexpy import activity_processor, helpers


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'normalized'


def configure_database(tmp_path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(tmp_path / 'tautulli.db'))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        BACKUP_DIR=str(tmp_path / 'backups'), BACKUP_DAYS=3,
        LOGGING_IGNORE_INTERVAL=0, NOTIFY_CONTINUED_SESSION_THRESHOLD=300,
    ))
    plexpy.dbcheck()


def load_session():
    session = json.loads((FIXTURES / 'session_base.json').read_text(encoding='utf-8'))
    session.update({
        'session_key': '101', 'started': 1704067200, 'stopped': 1704067800,
        'paused_counter': 0, 'product_version': '1', 'profile': '', 'video_bitrate': '7600',
        'video_bit_depth': '8', 'video_codec_level': '', 'video_width': '1920',
        'video_height': '1080', 'video_scan_type': 'progressive', 'audio_bitrate': '192',
        'audio_language': 'English', 'audio_language_code': 'eng', 'subtitle_codec': '',
        'subtitle_forced': 0, 'subtitle_language': '', 'transcode_hw_requested': 0,
        'transcode_hw_full_pipeline': 0, 'transcode_hw_decode': '',
        'transcode_hw_decode_title': '', 'transcode_hw_encode': '',
        'transcode_hw_encode_title': '', 'stream_video_bitrate': '7600',
        'stream_video_codec_level': '', 'stream_video_bit_depth': '8',
        'stream_video_scan_type': 'progressive', 'stream_video_full_resolution': '1080p',
        'stream_audio_bitrate': '192', 'stream_audio_language_code': 'eng',
        'stream_subtitle_container': '', 'stream_subtitle_forced': 0,
        'subtitles': 0, 'synced_version': 0, 'synced_version_profile': '',
        'optimized_version': 0, 'optimized_version_profile': '', 'optimized_version_title': '',
        'live': 0, 'secure': 1, 'relayed': 0,
    })
    return session


def load_metadata():
    metadata = json.loads((FIXTURES / 'metadata_movie.json').read_text(encoding='utf-8'))
    metadata['markers'] = []
    return metadata


def test_active_session_defaults_to_plex_provenance(tmp_path, monkeypatch):
    configure_database(tmp_path, monkeypatch)
    monkeypatch.setattr(helpers, 'timestamp', lambda: 1704067200)
    processor = activity_processor.ActivityProcessor()
    session = load_session()
    processor.write_session(session=session, notify=False)
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute(
        'SELECT media_backend, external_item_id, external_user_id, external_library_id, '
        'external_session_id FROM sessions'
    ).fetchone() == ('plex', None, None, None, None)
    connection.close()


def test_jellyfin_provenance_survives_active_to_history(tmp_path, monkeypatch):
    configure_database(tmp_path, monkeypatch)
    monkeypatch.setattr(helpers, 'timestamp', lambda: 1704067800)
    processor = activity_processor.ActivityProcessor()
    session = load_session()
    session.update({
        'media_backend': 'jellyfin', 'external_item_id': 'item-external',
        'external_user_id': 'user-external', 'external_library_id': 'library-external',
        'external_session_id': 'session-external',
    })
    processor.write_session(session=session, notify=False)
    persisted = processor.get_session_by_key(session['session_key'])
    assert persisted['media_backend'] == 'jellyfin'
    processor.write_session_history(
        session=copy.deepcopy(persisted), import_metadata=load_metadata(), is_import=True)
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute(
        'SELECT media_backend, external_item_id, external_user_id, external_library_id, '
        'external_session_id FROM session_history'
    ).fetchone() == (
        'jellyfin', 'item-external', 'user-external', 'library-external', 'session-external')
    connection.close()


def test_legacy_import_history_defaults_to_plex_provenance(tmp_path, monkeypatch):
    configure_database(tmp_path, monkeypatch)
    monkeypatch.setattr(helpers, 'timestamp', lambda: 1704067800)
    processor = activity_processor.ActivityProcessor()
    session = load_session()
    for key in ('media_backend', 'external_item_id', 'external_user_id',
                'external_library_id', 'external_session_id'):
        session.pop(key, None)
    processor.write_session_history(
        session=session, import_metadata=load_metadata(), is_import=True)
    connection = sqlite3.connect(plexpy.DB_FILE)
    assert connection.execute(
        'SELECT media_backend, external_item_id, external_user_id, external_library_id, '
        'external_session_id FROM session_history'
    ).fetchone() == ('plex', None, None, None, None)
    connection.close()
