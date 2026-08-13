# -*- coding: utf-8 -*-

"""Authoritative, restart-safe Jellyfin recently-added discovery."""

import plexpy
from plexpy import activity_handler, datafactory, helpers, logger
from plexpy.media_backend.factory import get_media_backend


def _notify_recent(metadata):
    activity_handler.on_created(
        metadata['rating_key'], metadata=metadata, pre_recorded=True)


def scan_recently_added(limit=100, notify=True):
    if getattr(plexpy.CONFIG, 'MEDIA_SERVER_TYPE', 'plex') != 'jellyfin':
        return 0
    backend = get_media_backend('jellyfin')
    server_id = backend.get_server_info()['machine_identifier']
    result = backend.get_recently_added(count=str(limit))
    discovered = 0
    for metadata in reversed(result.get('recently_added', [])):
        metadata = dict(metadata)
        metadata['server_id'] = server_id
        if not datafactory.DataFactory().set_recently_added_item(metadata=metadata):
            continue
        discovered += 1
        # Limit notifications to the scan recovery window. Older results are
        # recorded as the baseline and will not be emitted on every restart.
        if notify and helpers.cast_to_int(metadata.get('added_at')) >= helpers.timestamp() - 600:
            delay = max(0, helpers.cast_to_int(
                getattr(plexpy.CONFIG, 'NOTIFY_RECENTLY_ADDED_DELAY', 300)))
            activity_handler.schedule_callback(
                'jellyfin-created-{}-{}'.format(
                    metadata.get('external_item_id'), metadata.get('added_at')),
                func=_notify_recent, args=[metadata], seconds=delay)
    if discovered:
        logger.info('Jellyfin recently-added scan discovered %d new item(s).', discovered)
    return discovered
