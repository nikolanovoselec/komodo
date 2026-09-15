# Offline Now Playing geolocation

The collector resolves Plex `Player.address` against a local DB-IP Lite City MMDB. No viewer address is sent to DB-IP or another lookup provider. Only `geo_label` and `geo_status` reach the dashboard; raw addresses remain in memory. Existing LAN/WAN fields are preserved.

## Display semantics

- Public records: `≈ City, Country`, or country if the database has no city.
- Non-public addresses: `Local network`.
- Missing/invalid addresses: `Location unknown`.
- Known Plex relay: `Relay · location unknown`.
- Missing database, dependency or lookup failure: `Location unavailable`; session collection continues.

These are approximate network locations, not a person's precise location. VPN, proxy and mobile-network exits can differ from the viewer. No city is guessed when a record is unavailable.

## Deployment

`adapter/Dockerfile.geoip` retains the pinned Python base and adds `maxminddb==3.2.0`. The collector mounts the `geoip-city` named volume read-only. A credential-free one-shot `geoip-update` service writes the same volume and has no exposed ports. It normally exits with status 0. Collector availability does not depend on updater success.

The updater uses a fixed HTTPS origin, rejects redirects, bounds transfer time and compressed/expanded sizes, validates MMDB type, and publishes atomically. Failures retain the previous database. Valid same-month cache avoids another download. Docker initializes a new volume from an image directory owned by UID 65534.

All builds and deployment changes go through the tracked repository and Komodo. Do not install dependencies or copy database files directly onto production hosts.

## Monthly updates

1. Update the explicit `--month YYYY-MM` in the tracked updater command.
2. Validate Compose, commit and push through the normal Komodo workflow.
3. Verify the updater exited 0 and the database build month is the intended release.
4. Verify a public session has an approximate label and private sessions remain local. Never print source addresses during verification.

The collector detects atomic database replacements without restart. Preserve the named volume during upgrades. There is no automatic monthly scheduler: a failed or missed update leaves the last downloaded database, which may become stale. Reserve approximately 500 MB free disk for the old database plus temporary download files.

## Licensing and attribution

DB-IP Lite is monthly, account-free and licensed under CC BY 4.0. It has lower coverage and accuracy than paid databases. The Now Playing section includes the required visible [IP Geolocation by DB-IP](https://db-ip.com) attribution.

Official sources:
- https://db-ip.com/db/download/ip-to-city-lite
- https://db-ip.com/db/lite.php

## Verification

Backend tests cover classification, sanitized projection, reader reuse/reload, failure fallback, safe download, atomic replacement, cache reuse, redirect rejection and resource bounds. Tests use synthetic addresses. Additional validation used the real September 2026 MMDB with networking disabled and live Plex addresses in memory only. Deployment/UI contracts are in `test_geolocation_integration.py`; browser layout checks are in `qa_session_identity.py` and `qa_session_viewer.py`.
