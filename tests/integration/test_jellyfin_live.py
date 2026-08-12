import pytest

from plexpy.media_backend.errors import BackendAuthError, BackendNotFoundError, BackendServerError
from plexpy.media_backend.jellyfin import JellyfinClient, JellyfinImage


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

    with JellyfinClient(
            server.base_url, 'definitely-invalid-token',
            device_id='phase3-invalid-token') as invalid:
        with pytest.raises(BackendAuthError):
            invalid.connect()
