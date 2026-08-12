# Jellyfin Port Baseline

## Source

- Upstream project: `https://github.com/Tautulli/Tautulli.git`
- Upstream tag: `v2.17.2`
- Upstream commit: `c7153deb6e3017b8dda46c8448fe548a61c5a47a`
- Fork integration branch: `main`
- Active development branch: `jellyfin-port`
- Baseline recorded: 2026-08-12

The upstream Git history is retained. The first foundation build deliberately preserves Plex behavior while inserting a backend boundary; Jellyfin network support begins in a later phase.

## Repository workflow

`Liam-Atwood/Tautulli` is the independent project repository. Completed builds are developed and tested on `jellyfin-port`, then fast-forwarded into the fork's `main` branch. The `upstream` remote is retained only for source attribution and optional future reference; changes are not proposed or merged into `Tautulli/Tautulli`.

GitHub Actions runs the complete port suite directly on pushes to both `jellyfin-port` and `main`. Pull requests are not required for the fork's integration workflow.

## Target compatibility

- Primary Jellyfin target: 10.11.x
- Secondary Jellyfin target: 10.10.7
- Future major-version target: Jellyfin 12 through a separate backend compatibility implementation
- Supported Python test floor/current packaging target: Python 3.10 and Python 3.13

## Licensing

This fork inherits Tautulli's GNU GPL version 3 obligations. Modified distributions must retain the license and satisfy the GPL's source-availability requirements.

Tautulli also includes Highsoft/Highcharts assets whose bundled terms permit non-commercial distribution. Commercial distribution requires a separate Highsoft licensing review and, where applicable, a commercial license. GPL compliance does not replace that review.
