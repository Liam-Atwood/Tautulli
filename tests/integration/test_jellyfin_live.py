import pytest

from plexpy.media_backend.errors import BackendAuthError, BackendNotFoundError, BackendServerError
from plexpy.media_backend.jellyfin import (
    JellyfinActivityNormalizer, JellyfinClient, JellyfinImage, JellyfinMetadataAdapter,
)


class MemoryMapper:
    def __init__(self):
        self.values, self.reverse, self.next = {}, {}, 1000000000000

    def get_or_create(self, entity, external):
        key = entity, str(external)
        if key not in self.values:
            self.values[key] = self.next
            self.reverse[(entity, self.next)] = str(external)
            self.next += 1
        return self.values[key]

    def to_external(self, entity, local):
        return self.reverse.get((entity, int(local)))


pytestmark = [pytest.mark.integration, pytest.mark.allow_hosts(['127.0.0.1'])]


def test_supported_jellyfin_server_contract(jellyfin_server):
    server = jellyfin_server
    with JellyfinClient(
            server.base_url, server.token, device_id='phase3-live-contract') as client:
        info = client.connect()
        assert client.server_id == info['Id']
        assert client.server_version == info['Version']
        assert client.api_profile.name in ('10.10', '10.11')
        if server.expected_version:
            assert client.server_version.startswith(server.expected_version)

        sessions = client.get_sessions()
        assert isinstance(sessions, list)
        assert any(session.get('UserId') == server.user_id for session in sessions)

        users = client.get_users()
        assert any(user['Id'] == server.user_id for user in users)
        libraries = client.get_libraries()
        assert any(library['Name'] == 'Phase Three Music' for library in libraries)

        latest = client.get_latest_items(
            limit=10, include_item_types='Audio', user_id=server.user_id)
        assert any(item['Id'] == server.item_id for item in latest['Items'])
        searched = client.search_items('Phase Three Fixture', user_id=server.user_id)
        assert any(item['Id'] == server.item_id for item in searched['Items'])
        assert isinstance(client.get_collections(user_id=server.user_id), dict)
        assert isinstance(client.get_playlists(user_id=server.user_id), dict)
        assert isinstance(client.get_devices(), dict)
        assert isinstance(client.get_logs(), list)
        assert isinstance(client.get_live_tv_channels(user_id=server.user_id), dict)
        assert isinstance(client.get_live_tv_programs(user_id=server.user_id), dict)
        assert isinstance(client.get_live_tv_recordings(user_id=server.user_id), dict)

        items = client.get_items(
            recursive=True, searchTerm='Phase Three Fixture', includeItemTypes='Audio',
            fields=['Path', 'MediaSources'])
        assert items['Items'] and items['Items'][0]['Id'] == server.item_id
        item = client.get_item(server.item_id, user_id=server.user_id, fields=['MediaSources'])
        assert item['Id'] == server.item_id and item['MediaSources']

        image = client.get_image(server.item_id)
        assert isinstance(image, JellyfinImage) and image.data
        assert image.content_type.startswith('image/')

        with pytest.raises(BackendServerError) as missing_item:
            client.get_item('11111111111111111111111111111111')
        assert missing_item.value.status_code == 400
        with pytest.raises(BackendNotFoundError):
            client.get_image(server.item_id, image_type='Backdrop', image_index=99)

        mapper = MemoryMapper()
        adapter = JellyfinMetadataAdapter(client, mapper)
        metadata = adapter.get_metadata(server.item_id, user_id=server.user_id)
        assert metadata['media_type'] == 'track'
        assert metadata['rating_key'] >= 1000000000000
        assert metadata['media_info'] and metadata['media_info'][0]['parts'][0]['streams']

        activity = JellyfinActivityNormalizer(client, mapper, adapter).get_current_activity(
            skip_cache=True)
        playing = [session for session in activity['sessions']
                   if session['external_item_id'] == server.item_id]
        assert playing and playing[0]['state'] == 'playing'
        assert playing[0]['transcode_decision'] == 'direct play'
        assert activity['stream_count_direct_play'] >= 1

    with JellyfinClient(
            server.base_url, 'definitely-invalid-token',
            device_id='phase3-invalid-token') as invalid:
        with pytest.raises(BackendAuthError):
            invalid.connect()
