from types import SimpleNamespace

import plexpy
from plexpy import common
from plexpy.media_backend.jellyfin.activity import JellyfinActivityNormalizer
from plexpy.media_backend.jellyfin.metadata import JellyfinMetadataAdapter


class Client:
    server_id = 'server-a'

    def get_item(self, item_id, **kwargs):
        return {
            'Id': item_id, 'Type': 'LiveTvProgram', 'Name': 'Fixture News',
            'ChannelId': 'channel-a', 'ChannelName': 'Fixture TV', 'ChannelNumber': '7.1',
            'ProgramId': 'program-a', 'IsLive': True, 'RunTimeTicks': 18000000000,
            'StartDate': '2026-08-12T12:00:00Z', 'EndDate': '2026-08-12T12:30:00Z',
            'ImageTags': {'Primary': 'tag'}, 'MediaSources': [{'Id': 'source', 'Container': 'ts',
                'Bitrate': 4000000, 'RunTimeTicks': 18000000000, 'MediaStreams': [
                    {'Type': 'Video', 'Index': 0, 'Codec': 'h264', 'Height': 1080},
                    {'Type': 'Audio', 'Index': 1, 'Codec': 'aac', 'Channels': 2},
                ]}],
        }

    def get_ancestors(self, *args, **kwargs): return []
    def get_sessions(self, **kwargs): return []


class Mapper:
    def get_or_create(self, entity, external): return abs(hash((entity, external))) % 100000 + 1
    def to_external(self, entity, local): return None


def test_live_program_metadata_preserves_channel_and_synthetic_library(monkeypatch):
    adapter = JellyfinMetadataAdapter(Client(), Mapper())
    metadata = adapter.get_metadata('program-a')
    assert metadata['media_type'] == 'episode' and metadata['live'] == 1
    assert metadata['section_id'] == common.LIVE_TV_SECTION_ID
    assert metadata['library_name'] == common.LIVE_TV_SECTION_NAME
    assert metadata['channel_identifier'] == 'channel-a'
    assert metadata['channel_title'] == 'Fixture TV'
    assert metadata['channel_vcn'] == '7.1'
    assert metadata['external_program_id'] == 'program-a'


def test_live_program_activity_carries_channel_provenance(monkeypatch):
    client, mapper = Client(), Mapper()
    metadata = JellyfinMetadataAdapter(client, mapper)
    normalizer = JellyfinActivityNormalizer(client, mapper, metadata)
    raw = {'Id': 'session-a', 'UserId': 'user-a', 'UserName': 'Ada', 'DeviceId': 'device-a',
           'NowPlayingItem': client.get_item('program-a'),
           'PlayState': {'MediaSourceId': 'source', 'VideoStreamIndex': 0, 'AudioStreamIndex': 1,
                         'PositionTicks': 10000000, 'PlayMethod': 'DirectPlay'}}
    output = normalizer.normalize(raw, set())
    assert output['live'] == 1 and output['channel_identifier'] == 'channel-a'
    assert output['external_channel_id'] == 'channel-a'
    assert output['external_program_id'] == 'program-a'


def test_live_tv_client_endpoints_are_version_neutral(monkeypatch):
    client = Client()
    requests = []
    client._request = lambda method, endpoint, params=None: requests.append((method, endpoint, params)) or {}
    from plexpy.media_backend.jellyfin.client import JellyfinClient
    JellyfinClient.get_live_tv_channels(client, user_id='user')
    JellyfinClient.get_live_tv_programs(client, channel_ids=['a', 'b'])
    JellyfinClient.get_live_tv_recordings(client, user_id='user')
    JellyfinClient.get_live_tv_program(client, 'program')
    assert [endpoint for _, endpoint, _ in requests] == [
        'LiveTv/Channels', 'LiveTv/Programs', 'LiveTv/Recordings', 'LiveTv/Programs/program']
