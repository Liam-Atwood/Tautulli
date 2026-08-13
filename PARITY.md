# Jellyfin Port Parity Matrix

Statuses are evidence-based. `UNVERIFIED` means implementation or automated Jellyfin evidence is still pending; `N/A` is an inherently Plex-only concept; `REQUIRES TELEMETRY` cannot be supplied reliably by stock Jellyfin APIs. A feature may become `FULL` only after its acceptance tests pass.

| Tautulli feature | Initial status | Jellyfin strategy | Required evidence |
|---|---|---|---|
| Current activity | FULL | `/Sessions` normalization | Contract, polling, and live playback tests |
| Websocket session hints | FULL | Jellyfin `/socket` plus authoritative REST | Debounce, deduplication, reconnect, fallback, and lifecycle tests |
| Play history | FULL | Phase 7 lifecycle reconciler | `tests/test_jellyfin_lifecycle.py`: prerequisites, elapsed pauses, atomic bundle, rollback, exactly-once identity |
| Watch duration | FULL | Existing history calculations | Mixed-backend deterministic reporting fixture |
| Pause duration | FULL | Paused player state | Timestamp lifecycle and reporting tests |
| Watched threshold | FULL | Existing percentage calculation | Frozen reporting regression tests |
| Movie statistics | FULL | Existing database/reporting | Plex/Jellyfin equivalent report fixture |
| TV statistics | FULL | Existing hierarchy/reporting | Plex/Jellyfin episode report fixture |
| Music statistics | FULL | Existing hierarchy/reporting | Plex/Jellyfin track report fixture |
| User statistics | FULL | Existing database/reporting | Mapped multi-user fixture |
| Library statistics | FULL | Libraries plus existing reports | Mapped multi-library fixture |
| Platform/client statistics | FULL | Session client/device mapping | Activity and reporting contract tests |
| IP history | UNVERIFIED | `RemoteEndPoint` | IPv4/IPv6 lifecycle tests |
| Local/remote statistics | UNVERIFIED | CIDR classification | Network classification tests |
| Users | FULL | Jellyfin `/Users` policy normalization | Phase 8 authoritative sync and preference-preservation tests |
| Libraries | FULL | Jellyfin virtual folders and item totals | Phase 8 type/count and transactional replacement tests |
| Concurrent streams | FULL | Existing concurrency rules | Deterministic overlap report fixture |
| New-device notifications | UNVERIFIED | Stable `DeviceId` | Notification trigger test |
| Recently added | UNVERIFIED | Jellyfin item queries | Contract and ordering tests |
| Newsletters | UNVERIFIED | Existing renderer | Grouping and artwork tests |
| Metadata pages | FULL | `BaseItemDto` normalization | Media-type contract suite |
| Source media information | FULL | `MediaSourceInfo` | Source/selected-stream fixtures |
| Codec reporting | FULL | `MediaStream` | Codec contract fixtures |
| HDR and Dolby Vision | FULL | Structured stream fields | HDR10/HDR10+/DV fixtures |
| Direct Play | FULL | `PlayMethod` | Direct-play fixture and live playback report |
| Direct Stream | FULL | `PlayMethod` | Direct-stream fixture |
| Transcode | FULL | `PlayMethod` and transcoding data | Video/audio transcode fixtures |
| Hardware transcode indicator | UNVERIFIED | Hardware acceleration fields | Versioned integration fixture |
| Exact Plex decode/encode labels | N/A | Preserve only authoritative Jellyfin facts | Document semantic difference |
| Stream termination | UNVERIFIED | Session command where supported | Capability and integration tests |
| Pause/resume remote controls | UNVERIFIED | Media-control capability | Supported/unsupported client tests |
| Server up/down | FULL | Backend-neutral health connection | Startup success/failure tests |
| Authentication failure | FULL | Structured HTTP auth errors | 401/403 tests |
| Server update notification | UNVERIFIED | System/update API | Version-specific integration test |
| Search | UNVERIFIED | Search API | Cross-media search fixture |
| Collections | UNVERIFIED | BoxSet/collection APIs | Collection hierarchy test |
| Playlists | UNVERIFIED | Playlist API | Playlist item test |
| Live TV | UNVERIFIED | Live TV APIs | Channel/program/recording tests |
| Artwork | FULL | Token-safe image proxy | Fetch, transform, cache-header, and secret-leak tests |
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

Phase 1 is complete. The foundation gate freezes upstream normalized contracts, report outputs, and the full `PmsConnect` surface; automated signature, facade, factory, capability, error, import, and contract tests prove the abstraction preserves the Plex baseline.

## Phase 2 identity evidence

Phase 2 is complete. The database identity gate is covered by automated migration, mapper, persistence, import, and reporting tests. It establishes backend/server/entity-scoped string-to-integer mappings, globally unique JavaScript-safe surrogate IDs, and active/history provenance without changing the legacy Plex report or API surface.

Phase 2 does not promote any Jellyfin-facing feature to `FULL`: it contains no Jellyfin transport or live normalization. Current activity, history, users, libraries, devices, collections, and playlists remain `UNVERIFIED` until their later phase-specific integration tests pass.

## Phase 3 transport evidence

The standalone JSON-first client is verified against pinned Jellyfin 10.10.7 and 10.11.11 servers on Python 3.10 and 3.13. The live contract covers official MediaBrowser token authentication, system identity/version selection, sessions, item query/detail, users, virtual folders, image bytes, authentication failure, and missing resources. Offline tests cover URL and header validation, pooling, timeouts, safe retries, response decoding, error mapping, tracing, and secret redaction.

Phase 3 intentionally left `get_media_backend("jellyfin")` disabled. Phases 4–6 now provide the validated runtime path described below.

## Phase 4 setup evidence

Phase 4 is covered by configuration migration and alias tests, canonical-over-legacy environment precedence, token blacklisting and browser-form redaction, backend factory selection, server-identity validation, POST-only connection validation, and startup scheduler guards. Fresh installs default to Jellyfin; installations with any existing Plex identity remain Plex. Configuration is mutated only after validation and is rolled back in memory if persistence fails. Jellyfin startup performs a health connection without Plex.tv, websocket, discovery, user refresh, library refresh, server-update, or activity-monitor jobs.

## Phase 5 metadata evidence

Phase 5 normalizes Jellyfin movies, episodic items, music, photos, collections, playlists, recordings, and Live TV DTOs through one adapter. Contract tests cover hierarchy, globally mapped IDs, provider GUIDs, dates, people, tags, selected media sources, multi-stream data, HDR10+, structured Dolby Vision flags, and strict token-free image references. Image tests cover PNG/JPEG decoding, resize, crop, blur, opacity, background composition, corrupt input, content type, deterministic ETag, and the compatibility tuple boundary.

## Phase 6 activity evidence

Phase 6 is polling-only. Contract and fixture tests cover playing/paused sessions, direct play/direct stream/transcode decisions, selected streams, audio-only and subtitle paths, deterministic collision-safe session keys, IPv4/IPv6 CIDR classification, nullable TLS state, provenance, stable ordering, aggregate bandwidth, privacy masking, malformed records, caching, and `skip_cache`. The live matrix reports a real fixture playback session and validates the normalized metadata and current-activity output on Jellyfin 10.10.7 and 10.11.11 with Python 3.10 and 3.13. No scheduler invokes session reconciliation, and polling does not write active sessions, history, or notifications.

## Phases 7–10 evidence

Phase 7 connects normalized Jellyfin activity to the existing lifecycle reconciler with an independently bounded 5–60 second interval. Tests cover minimal user/library bootstrap, elapsed pause timestamps, notifications, watched calculations, restart-safe active rows, transactional three-table history writes, rollback, and exactly-once Jellyfin history identities.

Phase 8 performs libraries-first authoritative synchronization. Jellyfin policies and virtual-folder types/counts are normalized to the established user and library tables while local notification, history, guest, and custom-artwork preferences survive refreshes. Fetch failures cannot partially deactivate prior data.

Phase 9 compares the complete existing report output for equivalent Plex and Jellyfin histories with different numeric namespaces and provenance. Movie, television, music, users, libraries, platforms, durations, grouping, and concurrency are identical after normalizing identifiers.

Phase 10 adds `/socket` as a loss-tolerant hint channel. It uses the official MediaBrowser header, `SessionsStart` subscription, bounded message deduplication, 250 ms per-domain debounce, tolerant unknown-message handling, and capped reconnect backoff. Session hints invoke authoritative REST reconciliation; polling stays scheduled and websocket failure never changes REST-derived server health.
