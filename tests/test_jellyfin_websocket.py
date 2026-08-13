import json
import time
from types import SimpleNamespace

from plexpy.media_backend.jellyfin.websocket import JellyfinWebSocketClient, websocket_url


class Socket:
    def __init__(self): self.sent = []
    def send(self, value): self.sent.append(json.loads(value))
    def recv(self): return None
    def close(self): pass


def client():
    return SimpleNamespace(
        base_url='https://example.invalid/jellyfin', verify_ssl=True, timeout=(5, 30),
        session=SimpleNamespace(headers={'Authorization': 'MediaBrowser Token="secret"'}))


def test_reverse_proxy_websocket_url_and_official_auth_header():
    calls, socket = [], Socket()
    ws = JellyfinWebSocketClient(
        client(), lambda: None,
        create_connection=lambda *args, **kwargs: calls.append((args, kwargs)) or socket)
    ws._connect()
    assert calls[0][0][0] == 'wss://example.invalid/jellyfin/socket'
    assert calls[0][1]['header'] == {'Authorization': 'MediaBrowser Token="secret"'}
    assert socket.sent == [{'MessageType': 'SessionsStart', 'Data': '0,10000'}]


def test_session_messages_are_debounced_and_deduplicated():
    calls = []
    ws = JellyfinWebSocketClient(client(), lambda: calls.append('sessions'), debounce_seconds=.01)
    assert ws.process_message({'MessageType': 'PlaybackProgress', 'MessageId': '1'})
    assert not ws.process_message({'MessageType': 'PlaybackProgress', 'MessageId': '1'})
    assert ws.process_message({'MessageType': 'PlaybackStopped', 'MessageId': '2'})
    time.sleep(.04)
    assert calls == ['sessions']
    ws.close()


def test_library_user_keepalive_and_unknown_messages_are_safe():
    calls = []
    ws = JellyfinWebSocketClient(
        client(), lambda: None, lambda: calls.append('library'), lambda: calls.append('user'),
        debounce_seconds=.01, max_seen=2)
    assert ws.process_message({'MessageType': 'LibraryChanged', 'MessageId': '1'})
    assert ws.process_message({'MessageType': 'UserUpdated', 'MessageId': '2'})
    assert ws.process_message({'MessageType': 'KeepAlive'})
    assert not ws.process_message({'MessageType': 'FutureMessage', 'MessageId': '3'})
    assert not ws.process_message('not-json')
    time.sleep(.04)
    assert sorted(calls) == ['library', 'user']
    assert list(ws._seen) == ['2', '3']
    ws.close()


def test_socket_failure_does_not_invoke_rest_reconciler():
    calls = []
    ws = JellyfinWebSocketClient(
        client(), lambda: calls.append('rest'),
        create_connection=lambda *args, **kwargs: (_ for _ in ()).throw(OSError('offline')))
    ws._stop.wait = lambda delay: ws._stop.set() or True
    ws.run()
    assert calls == []
