import json
from pathlib import Path
from types import SimpleNamespace

import plexpy
from plexpy import datafactory, helpers


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'reporting'


def _configure_database(tmp_path, monkeypatch):
    monkeypatch.setattr(plexpy, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(plexpy, 'DB_FILE', str(tmp_path / 'tautulli.db'))
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(
        SYNCHRONOUS_MODE='OFF', JOURNAL_MODE='MEMORY', CACHE_SIZEMB=1,
        GROUP_HISTORY_TABLES=False, HISTORY_TABLE_ACTIVITY=False,
        HOME_STATS_CARDS=[], MOVIE_WATCHED_PERCENT=85, TV_WATCHED_PERCENT=85,
        MUSIC_WATCHED_PERCENT=85, WATCHED_MARKER=0))
    plexpy.dbcheck()
    connection = __import__('sqlite3').connect(plexpy.DB_FILE)
    connection.executescript((FIXTURES / 'history.sql').read_text(encoding='utf-8'))
    connection.commit()
    connection.close()
    monkeypatch.setattr(helpers, 'timestamp', lambda: 1705000000)


def _card(stats, card_id):
    return next(card for card in stats if card['stat_id'] == card_id)['rows'][0]


def test_existing_reporting_outputs_are_frozen(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    expected = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))
    cards = [
        'top_movies', 'popular_movies', 'top_tv', 'popular_tv', 'top_music', 'popular_music',
        'top_libraries', 'top_users', 'top_platforms', 'last_watched', 'most_concurrent']
    stats = datafactory.DataFactory().get_home_stats(time_range=30, stats_cards=cards)
    for card_id in ('top_movies', 'top_tv', 'top_music', 'top_users', 'top_platforms'):
        row = _card(stats, card_id)
        for key, value in expected[card_id].items():
            assert row[key] == value
    concurrent = _card(stats, 'most_concurrent')
    assert concurrent['count'] == expected['max_concurrent']
    assert _card(stats, 'popular_movies')['users_watched'] == 2
    assert _card(stats, 'popular_tv')['users_watched'] == 2
    assert _card(stats, 'popular_music')['users_watched'] == 1
    assert {row['section_id'] for card in stats if card['stat_id'] == 'top_libraries' for row in card['rows']} == {1, 2, 3}
    assert _card(stats, 'last_watched')['title'] == 'Example Series - S01 E02 - Second'


def test_existing_library_and_grouping_reports(tmp_path, monkeypatch):
    _configure_database(tmp_path, monkeypatch)
    expected = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))
    factory = datafactory.DataFactory()
    libraries = factory.get_library_stats(library_cards=['1', '2', '3'])
    section_ids = sorted(item['section_id'] for rows in libraries.values() for item in rows)
    assert section_ids == expected['library_sections']
    ungrouped = factory.get_home_stats(time_range=30, grouping=False, stats_cards=['top_movies'])
    grouped = factory.get_home_stats(time_range=30, grouping=True, stats_cards=['top_movies'])
    assert _card(ungrouped, 'top_movies')['total_plays'] == 2
    assert _card(grouped, 'top_movies')['total_plays'] == 2
