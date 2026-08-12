# -*- coding: utf-8 -*-

import hashlib
import ipaddress
import re
import threading
import time

from plexpy import common, helpers, session as session_helpers
from plexpy.media_backend.idmap import ENTITY_DEVICE, ENTITY_ITEM, ENTITY_LIBRARY, ENTITY_USER


DEFAULT_LOCAL_NETWORKS = ('127.0.0.0/8', '::1/128', '10.0.0.0/8', '172.16.0.0/12',
                          '192.168.0.0/16', 'fd00::/8')


def stable_session_key(server_id, external_session_id, used=None):
    used = used if used is not None else set()
    salt = 0
    while True:
        payload = '{}\0{}\0{}'.format(server_id, external_session_id, salt).encode('utf-8')
        value = int.from_bytes(hashlib.sha256(payload).digest()[:6], 'big') or 1
        if value not in used:
            used.add(value)
            return value
        salt += 1


def _endpoint_ip(value):
    value = str(value or '').strip()
    if value.startswith('['):
        return value[1:value.find(']')]
    if value.count(':') == 1:
        return value.rsplit(':', 1)[0]
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        match = re.match(r'^(.*):(\d+)$', value)
        return match.group(1) if match else value


def classify_endpoint(value, networks=DEFAULT_LOCAL_NETWORKS):
    raw = _endpoint_ip(value)
    try:
        address = ipaddress.ip_address(raw)
        local = any(address in ipaddress.ip_network(network, strict=False) for network in networks)
        return raw, int(local), 'lan' if local else 'wan'
    except ValueError:
        return raw, 0, 'wan'


class JellyfinActivityNormalizer:
    def __init__(self, client, mapper, metadata, local_networks=DEFAULT_LOCAL_NETWORKS,
                 cache_seconds=2):
        self.client, self.mapper, self.metadata = client, mapper, metadata
        self.local_networks = tuple(local_networks or DEFAULT_LOCAL_NETWORKS)
        self.cache_seconds = max(0, float(cache_seconds))
        self._cache = None
        self._lock = threading.Lock()

    def get_current_activity(self, skip_cache=False):
        now = time.monotonic()
        with self._lock:
            if not skip_cache and self._cache and now - self._cache[0] <= self.cache_seconds:
                return self._cache[1]
        sessions, used = [], set()
        for raw in self.client.get_sessions(activeWithinSeconds=90) or []:
            item = raw.get('NowPlayingItem')
            if not item or not item.get('Id'):
                continue
            try:
                sessions.append(self.normalize(raw, used, skip_cache))
            except Exception:
                continue
        sessions.sort(key=lambda value: int(value['session_key']))
        sessions = session_helpers.mask_session_info(sessions)
        result = {
            'stream_count': str(len(sessions)),
            'stream_count_direct_play': sum(s['transcode_decision'] == 'direct play' for s in sessions),
            'stream_count_direct_stream': sum(s['transcode_decision'] == 'copy' for s in sessions),
            'stream_count_transcode': sum(s['transcode_decision'] == 'transcode' for s in sessions),
            'total_bandwidth': sum(helpers.cast_to_int(s.get('bandwidth')) for s in sessions),
            'lan_bandwidth': sum(helpers.cast_to_int(s.get('bandwidth')) for s in sessions if s.get('location') == 'lan'),
            'wan_bandwidth': sum(helpers.cast_to_int(s.get('bandwidth')) for s in sessions if s.get('location') != 'lan'),
            'sessions': sessions,
        }
        with self._lock:
            self._cache = (now, result)
        return result

    def normalize(self, raw, used, skip_cache=False):
        item = raw['NowPlayingItem']
        external_session_id = str(raw.get('Id') or '{}:{}'.format(raw.get('DeviceId', ''), item['Id']))
        external_user_id = str(raw.get('UserId') or '')
        external_device_id = str(raw.get('DeviceId') or raw.get('Client') or external_session_id)
        play_state = raw.get('PlayState') or {}
        media_source_id = play_state.get('MediaSourceId')
        metadata = self.metadata.get_metadata(item['Id'], user_id=external_user_id or None,
                                              skip_cache=skip_cache,
                                              media_source_id=media_source_id)
        rich_item = self.metadata._fetch(item['Id'], external_user_id or None, skip_cache,
                                         media_source_id)
        media_source = self._source(rich_item, raw)
        video, audio, subtitle = self._streams(media_source, raw)
        transcode = raw.get('TranscodingInfo') or {}
        method = str(play_state.get('PlayMethod') or ('Transcode' if transcode else 'DirectPlay'))
        decision = {'DirectPlay': 'direct play', 'DirectStream': 'copy', 'Transcode': 'transcode'}.get(
            method, 'direct play')
        ip_address, local, location = classify_endpoint(raw.get('RemoteEndPoint'), self.local_networks)
        duration = int(item.get('RunTimeTicks') or media_source.get('RunTimeTicks') or 0) // 10000
        offset = int(play_state.get('PositionTicks') or 0) // 10000
        bitrate = transcode.get('Bitrate') or media_source.get('Bitrate') or 0
        session_key = stable_session_key(self.client.server_id, external_session_id, used)
        output = dict(metadata)
        output.update({
            'session_key': str(session_key), 'session_id': external_session_id,
            'external_session_id': external_session_id, 'media_backend': 'jellyfin',
            'external_item_id': item['Id'], 'external_user_id': external_user_id or None,
            'external_library_id': metadata.get('external_library_id'),
            'external_device_id': external_device_id,
            'rating_key': self.mapper.get_or_create(ENTITY_ITEM, item['Id']),
            'user_id': self.mapper.get_or_create(ENTITY_USER, external_user_id) if external_user_id else '',
            'machine_id': self.mapper.get_or_create(ENTITY_DEVICE, external_device_id),
            'username': raw.get('UserName', ''), 'user': raw.get('UserName', ''),
            'friendly_name': raw.get('UserName', ''), 'player': raw.get('DeviceName') or raw.get('Client', ''),
            'user_thumb': ('jellyfin://user/{}/Primary/0'.format(external_user_id)
                           if external_user_id and raw.get('UserPrimaryImageTag') else ''),
            'product': raw.get('Client', ''), 'product_version': raw.get('ApplicationVersion', ''),
            'platform': raw.get('DeviceType') or raw.get('Client', ''), 'platform_version': '',
            'platform_name': self._platform_name(raw.get('DeviceType') or raw.get('Client', '')),
            'device': raw.get('DeviceType') or raw.get('DeviceName', ''),
            'ip_address': ip_address, 'ip_address_public': ip_address, 'local': local, 'location': location,
            'secure': None, 'relayed': 0, 'relay_applicable': False,
            'state': 'paused' if play_state.get('IsPaused') else 'playing',
            'view_offset': str(offset), 'duration': str(duration),
            'progress_percent': str(helpers.get_percent(offset, duration)), 'live': int(bool(item.get('IsLive'))),
            'bandwidth': str(int(bitrate or 0) // 1000),
            'bandwidth_source': 'transcoder_target' if transcode.get('Bitrate') else
                                'source_bitrate' if media_source.get('Bitrate') else 'unavailable',
            'quality_profile': media_source.get('Name') or 'Original',
            'container': media_source.get('Container', ''), 'bitrate': media_source.get('Bitrate', ''),
            'width': video.get('Width', ''), 'height': video.get('Height', ''),
            'aspect_ratio': video.get('AspectRatio', ''), 'video_codec': video.get('Codec', ''),
            'video_bitrate': video.get('BitRate', ''), 'video_width': video.get('Width', ''),
            'video_height': video.get('Height', ''), 'video_resolution': self._resolution(video),
            'video_full_resolution': self._resolution(video), 'video_framerate': video.get('AverageFrameRate', ''),
            'video_profile': video.get('Profile', ''), 'audio_codec': audio.get('Codec', ''),
            'audio_bitrate': audio.get('BitRate', ''), 'audio_channels': audio.get('Channels', ''),
            'audio_profile': audio.get('Profile', ''), 'stream_container': transcode.get('Container') or media_source.get('Container', ''),
            'stream_bitrate': bitrate, 'stream_video_codec': transcode.get('VideoCodec') or video.get('Codec', ''),
            'stream_video_resolution': self._resolution(video), 'stream_video_width': transcode.get('Width') or video.get('Width', ''),
            'stream_video_height': transcode.get('Height') or video.get('Height', ''),
            'stream_video_framerate': video.get('AverageFrameRate', ''),
            'stream_video_dynamic_range': video.get('VideoRangeType') or video.get('VideoRange') or '',
            'stream_audio_codec': transcode.get('AudioCodec') or audio.get('Codec', ''),
            'stream_audio_channels': transcode.get('AudioChannels') or audio.get('Channels', ''),
            'stream_audio_language': audio.get('Language', ''), 'stream_subtitle_codec': subtitle.get('Codec', ''),
            'stream_subtitle_language': subtitle.get('Language', ''),
            'stream_container_decision': decision, 'stream_video_decision': decision if video else '',
            'stream_audio_decision': decision if audio else '', 'stream_subtitle_decision': 'transcode' if transcode and subtitle else '',
            'video_decision': decision if video else '', 'audio_decision': decision if audio else '',
            'subtitle_decision': 'transcode' if transcode and subtitle else '', 'transcode_decision': decision,
            'transcode_key': str(transcode.get('TranscodeReasons') or ''),
            'transcode_progress': int(round(helpers.get_percent(offset, duration))) if transcode else 0,
            'transcode_speed': str(transcode.get('TranscodingFramerate') or ''),
            'transcode_container': transcode.get('Container', ''), 'transcode_protocol': transcode.get('Protocol', ''),
            'transcode_video_codec': transcode.get('VideoCodec', ''), 'transcode_audio_codec': transcode.get('AudioCodec', ''),
            'transcode_audio_channels': transcode.get('AudioChannels', ''), 'transcode_width': transcode.get('Width', ''),
            'transcode_height': transcode.get('Height', ''),
            'transcode_hw_decoding': int(bool(transcode.get('HardwareAccelerationType'))),
            'transcode_hw_encoding': int(bool(transcode.get('HardwareAccelerationType'))),
        })
        return output

    @staticmethod
    def _source(item, raw):
        sources = item.get('MediaSources') or []
        selected = (raw.get('PlayState') or {}).get('MediaSourceId')
        return next((source for source in sources if source.get('Id') == selected), sources[0] if sources else {})

    @staticmethod
    def _streams(source, raw):
        state = raw.get('PlayState') or {}
        streams = source.get('MediaStreams') or []
        def selected(kind, index_key):
            matches = [stream for stream in streams if stream.get('Type') == kind]
            index = state.get(index_key)
            return next((stream for stream in matches if stream.get('Index') == index), matches[0] if matches else {})
        return selected('Video', 'VideoStreamIndex'), selected('Audio', 'AudioStreamIndex'), selected('Subtitle', 'SubtitleStreamIndex')

    @staticmethod
    def _resolution(stream):
        height = stream.get('Height')
        return str(height) if height else ''

    @staticmethod
    def _platform_name(platform):
        value = str(platform or '')
        return next((name for key, name in common.PLATFORM_NAMES.items() if key in value.lower()), 'default')
