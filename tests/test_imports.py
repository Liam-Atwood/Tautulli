import importlib


def test_known_pmsconnect_consumers_import_without_cycles():
    modules = (
        'plexpy.activity_handler', 'plexpy.activity_pinger', 'plexpy.activity_processor',
        'plexpy.datafactory', 'plexpy.libraries', 'plexpy.newsletters', 'plexpy.notifiers',
        'plexpy.notification_handler', 'plexpy.plextv', 'plexpy.webserve',
    )
    for module in modules:
        assert importlib.import_module(module)
