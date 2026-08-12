# Jellyfin Port Parity Matrix

Statuses are evidence-based. `UNVERIFIED` means implementation or automated Jellyfin evidence is still pending; `N/A` is an inherently Plex-only concept; `REQUIRES TELEMETRY` cannot be supplied reliably by stock Jellyfin APIs. A feature may become `FULL` only after its acceptance tests pass.

| Tautulli feature | Initial status | Jellyfin strategy | Required evidence |
|---|---|---|---|
| Current activity | UNVERIFIED | `/Sessions` normalization | Session contract and live integration tests |
| Play history | UNVERIFIED | Existing `ActivityProcessor` | Complete lifecycle creates one row |
| Watch duration | UNVERIFIED | Existing history calculations | Reporting regression tests |
| Pause duration | UNVERIFIED | Paused player state | Pause/resume lifecycle test |
| Watched threshold | UNVERIFIED | Existing percentage calculation | Threshold boundary tests |
| Movie statistics | UNVERIFIED | Existing database/reporting | Deterministic report fixture |
| TV statistics | UNVERIFIED | Existing hierarchy/reporting | Episode hierarchy report fixture |
| Music statistics | UNVERIFIED | Existing hierarchy/reporting | Track hierarchy report fixture |
| User statistics | UNVERIFIED | Existing database/reporting | Multi-user fixture |
| Library statistics | UNVERIFIED | Libraries plus existing reports | Multi-library fixture |
| Platform/client statistics | UNVERIFIED | Session client/device mapping | Contract and reporting tests |
| IP history | UNVERIFIED | `RemoteEndPoint` | IPv4/IPv6 lifecycle tests |
| Local/remote statistics | UNVERIFIED | CIDR classification | Network classification tests |
| Concurrent streams | UNVERIFIED | Existing concurrency rules | Simultaneous-session test |
| New-device notifications | UNVERIFIED | Stable `DeviceId` | Notification trigger test |
| Recently added | UNVERIFIED | Jellyfin item queries | Contract and ordering tests |
| Newsletters | UNVERIFIED | Existing renderer | Grouping and artwork tests |
| Metadata pages | UNVERIFIED | `BaseItemDto` normalization | Media-type contract suite |
| Source media information | UNVERIFIED | `MediaSourceInfo` | Source/selected-stream fixtures |
| Codec reporting | UNVERIFIED | `MediaStream` | Codec contract fixtures |
| HDR and Dolby Vision | UNVERIFIED | Structured stream fields | HDR10/HDR10+/DV fixtures |
| Direct Play | UNVERIFIED | `PlayMethod` | Direct-play fixture |
| Direct Stream | UNVERIFIED | `PlayMethod` | Direct-stream fixture |
| Transcode | UNVERIFIED | `PlayMethod` and transcoding data | Video/audio transcode fixtures |
| Hardware transcode indicator | UNVERIFIED | Hardware acceleration fields | Versioned integration fixture |
| Exact Plex decode/encode labels | N/A | Preserve only authoritative Jellyfin facts | Document semantic difference |
| Stream termination | UNVERIFIED | Session command where supported | Capability and integration tests |
| Pause/resume remote controls | UNVERIFIED | Media-control capability | Supported/unsupported client tests |
| Server up/down | UNVERIFIED | Backend-neutral health state machine | Outage/recovery tests |
| Authentication failure | UNVERIFIED | Structured HTTP auth errors | 401/403 tests |
| Server update notification | UNVERIFIED | System/update API | Version-specific integration test |
| Search | UNVERIFIED | Search API | Cross-media search fixture |
| Collections | UNVERIFIED | BoxSet/collection APIs | Collection hierarchy test |
| Playlists | UNVERIFIED | Playlist API | Playlist item test |
| Live TV | UNVERIFIED | Live TV APIs | Channel/program/recording tests |
| Artwork | UNVERIFIED | Token-safe image proxy | Image and secret-leak tests |
| User library access | UNVERIFIED | User policy folders | Restricted-user test |
| Plex Relay | N/A | Do not fabricate an equivalent | Capability remains false |
| Plex Pass | N/A | Remove premium gating later | UI and config audit |
| Plex cloud mobile push | N/A | Use generic agents or active-session messaging | Agent capability documentation |
| Exact client buffering | REQUIRES TELEMETRY | Optional telemetry extension | Stock and extended-mode tests |
| Offline Sync inventory | REQUIRES TELEMETRY | Optional client integration | Capability-gated tests |
| External reachability | UNVERIFIED | Backend-neutral external probe | Public endpoint test |
| Tautulli public API | UNVERIFIED | Preserve compatibility fields | API contract regression suite |
| Tautulli Remote | UNVERIFIED | Preserve compatible API surface | Client compatibility test |
| Notifications and conditions | UNVERIFIED | Existing evaluation over normalized data | Per-trigger/agent tests |
| Exports | UNVERIFIED | Existing exporter over normalized metadata | Export regression tests |
| Database backup | UNVERIFIED | Existing implementation unchanged | Backup/restore smoke test |
| Configuration backup | UNVERIFIED | Existing implementation unchanged | Round-trip test |
| Self-update | UNVERIFIED | Point to fork release source later | Update-channel test |

## Foundation evidence

The Phase 0–1 gate freezes upstream normalized contracts, report outputs, and the full `PmsConnect` surface. Passing these tests proves only that the abstraction preserves the Plex baseline; it does not promote Jellyfin features to `FULL`.

## Phase 2 identity evidence

The database identity gate is covered by automated migration, mapper, persistence, import, and reporting tests. It establishes backend/server/entity-scoped string-to-integer mappings, globally unique JavaScript-safe surrogate IDs, and active/history provenance without changing the legacy Plex report or API surface.

Phase 2 does not promote any Jellyfin-facing feature to `FULL`: it contains no Jellyfin transport or live normalization. Current activity, history, users, libraries, devices, collections, and playlists remain `UNVERIFIED` until their later phase-specific integration tests pass.
