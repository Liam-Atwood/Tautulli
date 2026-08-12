# -*- coding: utf-8 -*-

from plexpy.media_backend.base import MediaBackend
from plexpy.media_backend.capabilities import BackendCapabilities


PLEX_CAPABILITIES = BackendCapabilities(
    websocket_sessions=True,
    remote_session_stop=True,
    exact_buffer_events=True,
    live_tv=True,
    playlists=True,
    collections=True,
    server_update_status=True,
    remote_access_probe=True,
    offline_download_inventory=True,
    active_client_messages=True,
    exact_tls_session_state=True,
    exact_relay_state=True,
)


class PlexBackend(MediaBackend):
    """Adapter around the untouched Plex implementation."""

    def __init__(self, url=None, token=None):
        from plexpy.pmsconnect import _LegacyPmsConnect
        self.legacy = _LegacyPmsConnect(url=url, token=token)

    @property
    def capabilities(self):
        return PLEX_CAPABILITIES

    def __getattr__(self, name):
        return getattr(self.legacy, name)

    def get_server_info(self):
        return self.legacy.get_server_identity()

    def get_current_activity(self, skip_cache=False):
        return self.legacy.get_current_activity(skip_cache=skip_cache)

    def get_metadata_details(self, local_item_id, **kwargs):
        return self.legacy.get_metadata_details(rating_key=local_item_id, **kwargs)

    def get_item_children(self, local_item_id, **kwargs):
        return self.legacy.get_item_children(rating_key=local_item_id, **kwargs)

    def get_recently_added(self, **kwargs):
        return self.legacy.get_recently_added_details(**kwargs)

    def get_libraries(self):
        return self.legacy.get_library_details()

    def get_users(self):
        from plexpy import plextv
        return plextv.PlexTV().get_full_users_list()

    def search(self, query, **kwargs):
        return self.legacy.get_search_results(query=query, **kwargs)

    def get_image(self, image_ref, **kwargs):
        return self.legacy.get_image(img=image_ref, **kwargs)

    def terminate_session(self, session_id, message=None):
        return self.legacy.terminate_session(session_id=session_id, message=message or '')

    def get_devices(self):
        from plexpy import plextv
        return plextv.PlexTV().get_devices_list()

    def get_playlists(self, **kwargs):
        from plexpy import libraries
        return libraries.get_playlists_list(**kwargs)

    def get_collections(self, **kwargs):
        from plexpy import libraries
        return libraries.get_collections_list(**kwargs)

    def get_server_update_status(self):
        return self.legacy.get_update_staus()
