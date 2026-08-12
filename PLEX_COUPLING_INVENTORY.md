# Plex Coupling Inventory

This baseline inventory is produced by `scripts/audit_plex_coupling.py` using the ordered rules in `audit/plex_coupling_rules.json`. Run `python scripts/audit_plex_coupling.py --check` after changing first-party source, templates, packaging, documentation, or bundled `plexapi`.

Baseline captured from Tautulli `v2.17.2` plus the Phase 0–1 foundation on 2026-08-12:

| Classification | Matching lines | Files |
|---|---:|---:|
| Branding | 1,915 | 159 |
| Legacy-compatible identifier | 3,286 | 112 |
| Plex cloud dependency | 162 | 25 |
| Plex data model | 1,772 | 64 |
| Plex transport | 176 | 35 |
| Public API compatibility | 44 | 1 |
| UI assumption | 214 | 30 |
| **Unclassified** | **0** | **0** |

Counts are line classifications, not unique symbols. Rules are ordered so known network endpoints and transport headers take precedence over broader data-model, identifier, UI, and branding matches. The exact per-line JSON inventory is available with `--format json`; Markdown output groups affected files by classification.

## Classification policy

- `plex_cloud_dependency`: calls or references to Plex-operated network services.
- `plex_transport`: Plex headers, default ports, and transport-specific routes.
- `plex_data_model`: PlexTV, PlexServer/plexapi, and raw Plex object fields.
- `legacy_compatible_identifier`: stable internal names retained during the port.
- `ui_assumption`: Plex concepts embedded in templates or frontend behavior.
- `public_api_compatibility`: response/request names retained for clients.
- `branding`: prose or visual terminology with no stronger coupling classification.

The acceptance test requires every matching line to resolve to one of these categories. Classification documents coupling; it does not imply that a dependency is safe to retain in a Jellyfin runtime.
