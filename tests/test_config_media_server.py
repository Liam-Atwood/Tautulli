from pathlib import Path

from plexpy.config import Config


def make_config(tmp_path, body=''):
    path = tmp_path / 'config.ini'
    path.write_text(body, encoding='utf-8')
    return Config(str(path))


def test_fresh_config_is_jellyfin_first_and_idempotent(tmp_path):
    config = make_config(tmp_path)
    assert config.MEDIA_SERVER_TYPE == 'jellyfin'
    assert config.MEDIA_SERVER_VERIFY_TLS == 1
    assert config.CONFIG_VERSION == 23
    assert config.write() is True
    reloaded = Config(str(tmp_path / 'config.ini'))
    assert reloaded.MEDIA_SERVER_TYPE == 'jellyfin'
    assert reloaded.CONFIG_VERSION == 23


def test_existing_partial_plex_config_migrates_and_synchronizes_aliases(tmp_path):
    config = make_config(tmp_path, '''
[Advanced]
config_version = 22
[PMS]
pms_url = http://plex.internal:32400
pms_token = legacy-secret
pms_identifier = plex-server
pms_name = Living Room
''')
    assert config.MEDIA_SERVER_TYPE == 'plex'
    assert config.MEDIA_SERVER_URL == config.PMS_URL == 'http://plex.internal:32400'
    assert config.MEDIA_SERVER_TOKEN == config.PMS_TOKEN == 'legacy-secret'
    assert config.MEDIA_SERVER_ID == config.PMS_IDENTIFIER == 'plex-server'
    config.PMS_NAME = 'Renamed'
    assert config.MEDIA_SERVER_NAME == 'Renamed'
    config.MEDIA_SERVER_PUBLIC_URL = 'https://media.example'
    assert config.PMS_URL_OVERRIDE == 'https://media.example'


def test_canonical_environment_takes_precedence_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv('TAUTULLI_MEDIA_SERVER_URL', 'https://canonical.example')
    monkeypatch.setenv('TAUTULLI_PMS_URL', 'http://legacy.example:32400')
    config = make_config(tmp_path)
    assert config.MEDIA_SERVER_URL == 'https://canonical.example'
    assert config.PMS_URL == 'https://canonical.example'


def test_media_server_token_is_blacklisted_and_not_written_on_failure(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    config.MEDIA_SERVER_TOKEN = 'super-secret-token'
    config._blacklist()
    from plexpy import logger
    assert 'super-secret-token' in logger._BLACKLIST_WORDS

    def fail_write(*args, **kwargs):
        raise IOError('fixture failure')

    monkeypatch.setattr(type(config._config), 'write', fail_write)
    assert config.write() is False


def test_settings_template_never_renders_saved_token():
    template = Path('data/interfaces/default/settings.html').read_text(encoding='utf-8')
    assert 'id="media_server_token"' in template
    assert 'name="media_server_token" value=""' in template
    assert "config['media_server_token']" not in template
