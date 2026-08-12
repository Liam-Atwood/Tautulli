import copy
import json
from pathlib import Path
from types import SimpleNamespace
from xml.dom import minidom

import jsonschema
import pytest

import plexpy
from plexpy import pmsconnect


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / 'tests' / 'contracts'
FIXTURES = ROOT / 'tests' / 'fixtures'


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validator(name):
    schemas = [load_json(path) for path in CONTRACTS.glob('*.schema.json')]
    schema = next(item for item in schemas if item['$id'].endswith('/' + name))
    resolver = jsonschema.validators.RefResolver(
        base_uri=schema['$id'], referrer=schema,
        store={item['$id']: item for item in schemas})
    return jsonschema.Draft202012Validator(schema, resolver=resolver)


def session_cases():
    base = load_json(FIXTURES / 'normalized' / 'session_base.json')
    for case in load_json(FIXTURES / 'normalized' / 'session_cases.json'):
        session = copy.deepcopy(base)
        session.update(case['overrides'])
        yield case['name'], session


@pytest.mark.parametrize('name,normalized', list(session_cases()))
def test_normalized_session_fixtures_satisfy_legacy_contract(name, normalized):
    base_keys = set(load_json(FIXTURES / 'normalized' / 'session_base.json'))
    payload = {'stream_count': '1', 'sessions': [normalized]}
    validator('current_activity.schema.json').validate(payload)
    assert set(normalized) == base_keys
    assert normalized['session_key']
    assert normalized['transcode_decision'] in ('direct play', 'copy', 'transcode')


def test_metadata_and_recently_added_fixtures_satisfy_contracts():
    metadata = load_json(FIXTURES / 'normalized' / 'metadata_movie.json')
    recent = load_json(FIXTURES / 'normalized' / 'recently_added.json')
    validator('metadata.schema.json').validate(metadata)
    validator('recently_added.schema.json').validate(recent)
    assert recent['recently_added'][0]['added_at'] == '1704067200'


def _source_media(media_id, part_id, video_id, audio_id, subtitle_id=None):
    streams = [
        {'id': video_id, 'type': '1', 'video_codec': 'h264', 'video_codec_level': '',
         'video_bitrate': '7600', 'video_bit_depth': '8', 'video_chroma_subsampling': '',
         'video_color_primaries': '', 'video_color_range': '', 'video_color_space': '',
         'video_color_trc': '', 'video_dynamic_range': 'SDR', 'video_frame_rate': '24p',
         'video_ref_frames': '', 'video_height': '1080', 'video_width': '1920',
         'video_language': '', 'video_language_code': '', 'video_scan_type': 'progressive',
         'video_profile': 'high'},
        {'id': audio_id, 'type': '2', 'audio_codec': 'aac', 'audio_bitrate': '192',
         'audio_bitrate_mode': '', 'audio_channels': '2', 'audio_channel_layout': 'stereo',
         'audio_sample_rate': '48000', 'audio_language': 'English', 'audio_language_code': 'eng',
         'audio_profile': 'lc'},
    ]
    if subtitle_id:
        streams.append({'id': subtitle_id, 'type': '3', 'subtitle_codec': 'srt',
                        'subtitle_container': '', 'subtitle_format': '', 'subtitle_forced': 0,
                        'subtitle_location': '', 'subtitle_language': 'English',
                        'subtitle_language_code': 'eng'})
    return [{
        'id': media_id, 'container': 'mkv', 'bitrate': '8000', 'width': '1920', 'height': '1080',
        'aspect_ratio': '1.78', 'video_codec': 'h264', 'video_resolution': '1080',
        'video_full_resolution': '1080p', 'video_framerate': '24p', 'video_profile': 'high',
        'audio_codec': 'aac', 'audio_channels': '2', 'audio_profile': 'lc',
        'parts': [{'id': part_id, 'container': 'mkv', 'streams': streams}],
    }]


@pytest.mark.parametrize('fixture_name,expected', [
    ('session_movie_direct_play.xml', ('movie', 'playing', 'direct play')),
    ('session_episode_transcode.xml', ('episode', 'playing', 'transcode')),
    ('session_movie_paused.xml', ('movie', 'paused', 'direct play')),
    ('session_music.xml', ('track', 'playing', 'direct play')),
])
def test_legacy_xml_session_normalizer(monkeypatch, fixture_name, expected):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(PMS_VERSION='1.40.0', METADATA_CACHE_SECONDS=1800))
    monkeypatch.setattr(pmsconnect.users, 'Users', lambda: SimpleNamespace(
        get_details=lambda **kwargs: {'user_id': 1, 'username': 'fixture-admin',
                                      'friendly_name': 'Fixture Admin'}))
    document = minidom.parse(str(FIXTURES / 'plex' / fixture_name))
    item = next(node for name in ('Video', 'Track') for node in document.getElementsByTagName(name))
    session_key = item.getAttribute('sessionKey')
    cases = dict(session_cases())
    normalized_metadata = copy.deepcopy(cases[{
        '11': 'movie_direct_play', '12': 'episode_transcode',
        '13': 'paused_movie', '14': 'music_track'}[session_key]])
    media = item.getElementsByTagName('Media')[0]
    part = item.getElementsByTagName('Part')[0]
    streams = item.getElementsByTagName('Stream')
    video = next((s.getAttribute('id') for s in streams if s.getAttribute('streamType') == '1'), 'video-none')
    audio = next(s.getAttribute('id') for s in streams if s.getAttribute('streamType') == '2')
    subtitle = next((s.getAttribute('id') for s in streams if s.getAttribute('streamType') == '3'), None)
    normalized_metadata['media_info'] = _source_media(media.getAttribute('id'), part.getAttribute('id'),
                                                     video, audio, subtitle)
    legacy = pmsconnect._LegacyPmsConnect.__new__(pmsconnect._LegacyPmsConnect)
    legacy.get_metadata_details = lambda **kwargs: copy.deepcopy(normalized_metadata)
    result = legacy.get_session_each(item)
    assert (result['media_type'], result['state'], result['transcode_decision']) == expected
    validator('current_activity.schema.json').validate({'stream_count': '1', 'sessions': [result]})


def test_legacy_metadata_xml_normalizer(monkeypatch):
    monkeypatch.setattr(plexpy, 'CONFIG', SimpleNamespace(PMS_VERSION='1.40.0'))
    document = minidom.parse(str(FIXTURES / 'plex' / 'metadata_episode.xml'))
    empty = minidom.parseString('<MediaContainer size="0"/>')
    legacy = pmsconnect._LegacyPmsConnect.__new__(pmsconnect._LegacyPmsConnect)
    legacy.get_metadata = lambda rating_key, **kwargs: document if rating_key == '202' else empty
    result = legacy.get_metadata_details(rating_key='202')
    validator('metadata.schema.json').validate(result)
    assert (result['media_type'], result['parent_rating_key'], result['grandparent_rating_key']) == (
        'episode', '201', '200')


def test_empty_current_activity_shape(monkeypatch):
    document = minidom.parseString('<MediaContainer size="0"/>')
    legacy = pmsconnect._LegacyPmsConnect.__new__(pmsconnect._LegacyPmsConnect)
    legacy.get_sessions = lambda output_format='': document
    assert legacy.get_current_activity() == {'stream_count': '0', 'sessions': []}


def test_malformed_current_activity_response_is_stable(monkeypatch):
    legacy = pmsconnect._LegacyPmsConnect.__new__(pmsconnect._LegacyPmsConnect)
    legacy.get_sessions = lambda output_format='': None
    assert legacy.get_current_activity() == []
