import base64
from dataclasses import dataclass, field
import os
import shutil
import socket
import subprocess
import time
import uuid
import wave

import pytest
import requests

from plexpy.media_backend.jellyfin import build_authorization_header


DEFAULT_IMAGE = (
    'jellyfin/jellyfin:10.11.11@'
    'sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db'
)
ARTWORK = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


@dataclass(frozen=True)
class LiveJellyfinServer:
    base_url: str
    token: str = field(repr=False)
    user_token: str = field(repr=False)
    item_id: str
    user_id: str
    expected_version: str | None


def _free_port():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def _request(method, url, expected=(200, 204), **kwargs):
    response = requests.request(method, url, timeout=15, **kwargs)
    if response.status_code not in expected:
        raise RuntimeError(
            '{} {} returned {}: {}'.format(method, url, response.status_code, response.text[:500]))
    return response


def _write_media(media_dir):
    album = media_dir / 'Phase Three Album'
    album.mkdir(parents=True)
    with wave.open(str(album / 'Phase Three Fixture.wav'), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b'\x00\x00' * 8000)
    (album / 'folder.png').write_bytes(ARTWORK)


def _wait_for_library_scan(base_url, admin_header):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        tasks = _request(
            'GET', base_url + '/ScheduledTasks', expected=(200,), headers=admin_header).json()
        scan_tasks = [task for task in tasks if task.get('Name') == 'Scan Media Library']
        if scan_tasks and all(task.get('State') == 'Idle' for task in scan_tasks):
            return
        time.sleep(1)
    raise RuntimeError('Jellyfin library scan did not become idle within 120 seconds')


def _wait_for_server(base_url):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            response = requests.get(base_url + '/Startup/Configuration', timeout=3)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError('Jellyfin did not become ready within 120 seconds')


def _provision(base_url):
    _request('POST', base_url + '/Startup/Configuration', json={
        'UICulture': 'en-US', 'MetadataCountryCode': 'US',
        'PreferredMetadataLanguage': 'en',
    })
    # The GET initializes the first user on a brand-new database.
    _request('GET', base_url + '/Startup/User', expected=(200,))
    _request('POST', base_url + '/Startup/User', json={
        'Name': 'phase3-admin', 'Password': 'phase3-password',
    })
    _request('POST', base_url + '/Startup/RemoteAccess', json={
        'EnableRemoteAccess': False, 'EnableAutomaticPortMapping': False,
    })
    _request('POST', base_url + '/Startup/Complete')
    unauthenticated_header = build_authorization_header(
        token='provisioning-placeholder', client='TautulliTests', device='GitHubActions',
        device_id='phase3-provisioner', version='1')
    # Authentication requires the client identity fields but no Token attribute.
    unauthenticated_header = unauthenticated_header.rsplit(', Token=', 1)[0]
    auth = _request(
        'POST', base_url + '/Users/AuthenticateByName', expected=(200,),
        headers={'Authorization': unauthenticated_header},
        json={'Username': 'phase3-admin', 'Pw': 'phase3-password'},
    ).json()
    admin_header = {'Authorization': build_authorization_header(
        token=auth['AccessToken'], client='TautulliTests', device='GitHubActions',
        device_id='phase3-provisioner', version='1')}
    _request('POST', base_url + '/Auth/Keys', headers=admin_header, params={'app': 'Tautulli Phase 3'})
    keys = _request('GET', base_url + '/Auth/Keys', expected=(200,), headers=admin_header).json()
    key = next(item for item in keys['Items'] if item['AppName'] == 'Tautulli Phase 3')
    api_header = {'Authorization': build_authorization_header(
        token=key['AccessToken'], client='TautulliTests', device='GitHubActions',
        device_id='phase3-client', version='1')}
    _request(
        'POST', base_url + '/Library/VirtualFolders', headers=admin_header,
        params={
            'name': 'Phase Three Music', 'collectionType': 'music',
            'paths': '/media', 'refreshLibrary': 'true',
        }, json={},
    )
    deadline = time.monotonic() + 120
    item = None
    while time.monotonic() < deadline:
        result = _request(
            'GET', base_url + '/Items', expected=(200,), headers=api_header,
            params={
                'Recursive': 'true', 'SearchTerm': 'Phase Three Fixture',
                'IncludeItemTypes': 'Audio', 'Fields': 'Path,MediaSources',
            },
        ).json()
        if result.get('Items'):
            item = result['Items'][0]
            break
        time.sleep(2)
    if not item:
        raise RuntimeError('Jellyfin did not scan the fixture item within 120 seconds')
    _wait_for_library_scan(base_url, admin_header)
    _request(
        'POST', '{}/Items/{}/Images/Primary'.format(base_url, item['Id']),
        headers=dict(admin_header, **{'Content-Type': 'image/png'}),
        data=base64.b64encode(ARTWORK),
    )
    image_url = '{}/Items/{}/Images/Primary/0'.format(base_url, item['Id'])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = requests.get(image_url, headers=api_header, timeout=15)
        if response.status_code == 200 and response.content:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Jellyfin did not make the fixture artwork available within 30 seconds')
    media_source = item.get('MediaSources', [{}])[0]
    play_session_id = uuid.uuid4().hex
    playback = {
        'CanSeek': True, 'ItemId': item['Id'], 'MediaSourceId': media_source.get('Id'),
        'AudioStreamIndex': 0, 'SubtitleStreamIndex': None, 'IsPaused': False,
        'IsMuted': False, 'PositionTicks': 10000000, 'PlaybackRate': 1,
        'PlayMethod': 'DirectPlay', 'PlaySessionId': play_session_id,
        'RepeatMode': 'RepeatNone',
    }
    _request('POST', base_url + '/Sessions/Playing', headers=admin_header, json=playback)
    return LiveJellyfinServer(
        base_url=base_url,
        token=key['AccessToken'],
        user_token=auth['AccessToken'],
        item_id=item['Id'],
        user_id=auth['User']['Id'],
        expected_version=os.environ.get('JELLYFIN_TEST_VERSION'),
    )


@pytest.fixture(scope='session')
def jellyfin_server(tmp_path_factory):
    if not shutil.which('docker'):
        pytest.skip('Docker is required for Jellyfin integration tests')
    image = os.environ.get('JELLYFIN_TEST_IMAGE', DEFAULT_IMAGE)
    root = tmp_path_factory.mktemp('jellyfin-live')
    media_dir = root / 'media'
    config_dir = root / 'config'
    cache_dir = root / 'cache'
    for directory in (media_dir, config_dir, cache_dir):
        directory.mkdir()
    _write_media(media_dir)
    port = _free_port()
    name = 'tautulli-phase3-{}'.format(uuid.uuid4().hex[:12])
    command = [
        'docker', 'run', '--detach', '--rm', '--name', name,
        '--publish', '127.0.0.1:{}:8096'.format(port),
        '--volume', '{}:/config'.format(config_dir),
        '--volume', '{}:/cache'.format(cache_dir),
        '--volume', '{}:/media:ro'.format(media_dir),
        '--env', 'JELLYFIN_PublishedServerUrl=http://127.0.0.1:{}'.format(port),
        image,
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    base_url = 'http://127.0.0.1:{}'.format(port)
    try:
        _wait_for_server(base_url)
        yield _provision(base_url)
    except Exception:
        subprocess.run(['docker', 'logs', name], check=False)
        raise
    finally:
        subprocess.run(['docker', 'rm', '--force', name], check=False, stdout=subprocess.PIPE)
