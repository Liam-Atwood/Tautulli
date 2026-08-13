# -*- coding: utf-8 -*-

import json
import ssl
import threading
from collections import OrderedDict
from urllib.parse import urlsplit, urlunsplit

import websocket

from plexpy import logger


SESSION_MESSAGES = frozenset({'Sessions', 'SessionStarted', 'SessionEnded', 'PlaybackStart',
                              'PlaybackStopped', 'PlaybackProgress', 'Playstate', 'SessionInfo',
                              'TranscodingInfo'})
LIBRARY_MESSAGES = frozenset({'LibraryChanged', 'PackageInstallationCompleted', 'RefreshProgress'})
USER_MESSAGES = frozenset({'UserDataChanged', 'UserUpdated', 'UserDeleted'})


def websocket_url(base_url):
    parsed = urlsplit(base_url)
    return urlunsplit(('wss' if parsed.scheme == 'https' else 'ws', parsed.netloc,
                       parsed.path.rstrip('/') + '/socket', '', ''))


class JellyfinWebSocketClient:
    """Loss-tolerant hint channel; REST remains authoritative."""

    def __init__(self, client, reconcile, refresh_libraries=None, refresh_users=None,
                 create_connection=None, debounce_seconds=.25, max_seen=256):
        self.client, self.reconcile = client, reconcile
        self.refresh_libraries = refresh_libraries or (lambda: None)
        self.refresh_users = refresh_users or (lambda: None)
        self._create_connection = create_connection or websocket.create_connection
        self.debounce_seconds, self.max_seen = debounce_seconds, max_seen
        self._seen, self._timers = OrderedDict(), {}
        self._socket = self._thread = None
        self._stop = threading.Event()

    @property
    def connected(self):
        return self._socket is not None and not self._stop.is_set()

    def start(self):
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name='JellyfinWebSocket', daemon=True)
        self._thread.start()
        return self._thread

    def close(self):
        self._stop.set()
        for timer in list(self._timers.values()):
            timer.cancel()
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        self._socket = None

    def _debounce(self, name, callback):
        previous = self._timers.pop(name, None)
        if previous:
            previous.cancel()
        timer = threading.Timer(self.debounce_seconds, callback)
        timer.daemon = True
        self._timers[name] = timer
        timer.start()

    def process_message(self, payload):
        try:
            message = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
        except (TypeError, ValueError):
            logger.debug("Jellyfin WebSocket :: Ignoring malformed message.")
            return False
        if not isinstance(message, dict):
            return False
        identity = message.get('MessageId') or message.get('Id')
        if identity:
            identity = str(identity)
            if identity in self._seen:
                return False
            self._seen[identity] = None
            while len(self._seen) > self.max_seen:
                self._seen.popitem(last=False)
        kind = str(message.get('MessageType') or '')
        if kind in SESSION_MESSAGES:
            self._debounce('sessions', self.reconcile)
        elif kind in LIBRARY_MESSAGES:
            self._debounce('libraries', self.refresh_libraries)
        elif kind in USER_MESSAGES:
            self._debounce('users', self.refresh_users)
        elif kind == 'KeepAlive':
            return True
        else:
            logger.debug("Jellyfin WebSocket :: Ignoring unknown message type '%s'.", kind)
            return False
        return True

    def _connect(self):
        headers = {'Authorization': self.client.session.headers['Authorization']}
        sslopt = None if self.client.verify_ssl else {'cert_reqs': ssl.CERT_NONE}
        self._socket = self._create_connection(
            websocket_url(self.client.base_url), header=headers,
            timeout=self.client.timeout[1], sslopt=sslopt)
        self._socket.send(json.dumps({'MessageType': 'SessionsStart', 'Data': '0,10000'}))

    def run(self):
        delays, failures = (1, 2, 5, 10, 30), 0
        while not self._stop.is_set():
            try:
                self._connect()
                failures = 0
                logger.info("Jellyfin WebSocket :: Connected.")
                while not self._stop.is_set():
                    payload = self._socket.recv()
                    if payload is None:
                        raise websocket.WebSocketConnectionClosedException()
                    self.process_message(payload)
            except Exception as error:
                if self._stop.is_set():
                    break
                logger.warn("Jellyfin WebSocket :: Hint channel unavailable: %s", error)
                self._socket = None
                delay = delays[min(failures, len(delays) - 1)]
                failures += 1
                self._stop.wait(delay)
