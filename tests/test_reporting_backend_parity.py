import sqlite3
from pathlib import Path
from types import SimpleNamespace

import plexpy
from plexpy import datafactory, helpers
from plexpy.database import EXTERNAL_ID_FLOOR


FIXTURE = Path(__file__).parent / 'fixtures' / 'reporting' / 'history.sql'
CARDS = ['top_movies', 'top_tv', 'top_music', 'popular_movies', 'popular_tv',
         'popular_music', 'top_users', 'top_libraries', 'most_concurrent']


def configure(path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(path.parent))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(path))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        GROUP_HISTORY_TABLES=False, HISTORY_TABLE_ACTIVITY=False, HOME_STATS_CARDS=[],
        MOVIE_WATCHED_PERCENT=85, TV_WATCHED_PERCENT=85,
        MUSIC_WATCHED_PERCENT=85, WATCHED_MARKER=0))
    plexpy.dbcheck()
    connection = sqlite3.connect(path)
    connection.executescript(FIXTURE.read_text(encoding='utf-8'))
    connection.commit()
    connection.close()
    monkeypatch.setattr(helpers, 'timestamp', lambda: 1705000000)


def convert_to_jellyfin(path):
    offset = EXTERNAL_ID_FLOOR
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE session_history SET media_backend='jellyfin', external_item_id='item-' || rating_key, "
        "external_user_id='user-' || user_id, external_library_id='library-' || section_id, "
        "external_session_id='session-' || id, history_identity='history-' || id, "
        "rating_key=rating_key+?, user_id=user_id+?, section_id=section_id+?, "
        "parent_rating_key=CASE WHEN parent_rating_key > 0 THEN parent_rating_key+? ELSE 0 END, "
        "grandparent_rating_key=CASE WHEN grandparent_rating_key > 0 THEN grandparent_rating_key+? ELSE 0 END",
        [offset, offset, offset, offset, offset])
    connection.execute('UPDATE users SET user_id=user_id+?', [offset])
    connection.execute('UPDATE library_sections SET section_id=section_id+?', [offset])
    connection.execute(
        'UPDATE session_history_metadata SET rating_key=rating_key+?, '
        'parent_rating_key=CASE WHEN parent_rating_key > 0 THEN parent_rating_key+? ELSE 0 END, '
        'grandparent_rating_key=CASE WHEN grandparent_rating_key > 0 THEN grandparent_rating_key+? ELSE 0 END',
        [offset, offset, offset])
    connection.execute('UPDATE session_history_media_info SET rating_key=rating_key+?', [offset])
    connection.commit()
    connection.close()


def normalize_ids(value):
    if isinstance(value, dict):
        return {key: normalize_ids(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_ids(item) for item in value]
    if isinstance(value, int) and value >= EXTERNAL_ID_FLOOR:
        return value - EXTERNAL_ID_FLOOR
    if isinstance(value, str) and value.isdigit() and int(value) >= EXTERNAL_ID_FLOOR:
        return str(int(value) - EXTERNAL_ID_FLOOR)
    return value


def test_plex_and_jellyfin_histories_produce_identical_reports(tmp_path, monkeypatch):
    plex_path = tmp_path / 'plex.db'
    configure(plex_path, monkeypatch)
    plex_stats = datafactory.DataFactory().get_home_stats(time_range=30, stats_cards=CARDS)
    plex_libraries = datafactory.DataFactory().get_library_stats(library_cards=['1', '2', '3'])

    jellyfin_path = tmp_path / 'jellyfin.db'
    configure(jellyfin_path, monkeypatch)
    convert_to_jellyfin(jellyfin_path)
    jellyfin_stats = datafactory.DataFactory().get_home_stats(time_range=30, stats_cards=CARDS)
    jellyfin_libraries = datafactory.DataFactory().get_library_stats(
        library_cards=[str(EXTERNAL_ID_FLOOR + value) for value in (1, 2, 3)])

    assert normalize_ids(jellyfin_stats) == plex_stats
    assert normalize_ids(jellyfin_libraries) == plex_libraries


def test_mapped_user_library_date_grouping_and_network_filters(tmp_path, monkeypatch):
    path = tmp_path / 'tautulli.db'
    configure(path, monkeypatch)
    monkeypatch.setattr('plexpy.session.mask_session_info', lambda rows, **kwargs: rows)
    convert_to_jellyfin(path)
    factory = datafactory.DataFactory()
    user_id = EXTERNAL_ID_FLOOR + 1
    library_id = EXTERNAL_ID_FLOOR + 2
    filtered = factory.get_home_stats(
        time_range=30, grouping=True, user_id=user_id, section_id=library_id,
        after='2024-01-01', before='2024-01-12',
        stats_cards=['top_tv', 'top_platforms', 'most_concurrent'])
    tv = next(card for card in filtered if card['stat_id'] == 'top_tv')
    assert tv['rows'] and all(row['section_id'] == library_id for row in tv['rows'])
    connection = sqlite3.connect(path)
    assert connection.execute(
        "SELECT SUM(bandwidth), COUNT(*) FROM session_history WHERE media_backend='jellyfin' "
        "AND location='lan'").fetchone() == (16320, 3)
    assert connection.execute(
        "SELECT SUM(bandwidth), COUNT(*) FROM session_history WHERE media_backend='jellyfin' "
        "AND location='wan'").fetchone() == (8000, 2)
    connection.close()
