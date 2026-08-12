# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod


class MediaBackend(ABC):
    """Canonical operations exposed by a normalized media-server backend."""

    @abstractmethod
    def get_server_info(self):
        raise NotImplementedError

    @abstractmethod
    def get_current_activity(self, skip_cache=False):
        raise NotImplementedError

    @abstractmethod
    def get_metadata_details(self, local_item_id, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def get_item_children(self, local_item_id, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def get_recently_added(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def get_libraries(self):
        raise NotImplementedError

    @abstractmethod
    def get_users(self):
        raise NotImplementedError

    @abstractmethod
    def search(self, query, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def get_image(self, image_ref, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def terminate_session(self, session_id, message=None):
        raise NotImplementedError

    @abstractmethod
    def get_devices(self):
        raise NotImplementedError

    @abstractmethod
    def get_playlists(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def get_collections(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def get_server_update_status(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self):
        raise NotImplementedError
