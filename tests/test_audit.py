import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('audit_plex_coupling', ROOT / 'scripts' / 'audit_plex_coupling.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_every_plex_coupling_match_is_classified():
    matches = AUDIT.audit()
    assert matches
    assert not [match for match in matches if match['category'] is None]
    categories = {match['category'] for match in matches}
    assert {
        'branding', 'legacy_compatible_identifier', 'plex_cloud_dependency', 'plex_data_model',
        'plex_transport', 'public_api_compatibility', 'ui_assumption',
    } <= categories


def test_rules_are_machine_readable_and_inventory_is_present():
    config = AUDIT.load_rules()
    assert config['schema_version'] == 1
    assert (ROOT / 'PLEX_COUPLING_INVENTORY.md').is_file()


def test_generated_inventory_does_not_audit_itself():
    assert not any(
        match['path'] == 'PLEX_COUPLING_INVENTORY.md' for match in AUDIT.audit()
    )
