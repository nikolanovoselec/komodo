# Pi-hole v6 integration

The NETWORKING collector reads both `pihole-master.lan` (192.168.5.162) and `pihole-slave.lan` (192.168.5.92). Reuses the existing protected Komodo `PIHOLE_API_KEY` for both; `komodo_core/main.toml` references it and Compose injects it into **workload-summary only**. No credential is placed in frontend configuration or source control.

## Security and semantics
- HTTPS leaf SHA-256 pins independently matched against SSH-local certificates on both Pi-holes. Pin verification precedes password/SID transmission on every connection. Certificate rotation fails closed; reverify independently before updating the pin.
- Only session login/logout and read-only summary/query API calls; no DNS setting changes.
- Requests use 3-second socket inactivity timeouts and 256-KiB response limits. Async single-flight snapshot refresh, ten-second retry, thirty-second expiry. Inactivity timeout is not a total refresh deadline; a stalled refresh yields unavailable after expiry rather than accumulating workers.
- Totals sum available instances. Partial failures are visibly labelled; complete failure yields null/unavailable rather than zero.
- Gravity entries are summed, **not deduplicated unique domains**.
- Latest ten permitted and blocked query records merge both sources chronologically, retaining source, actual whitelisted status, domain and UTC time only. Permitted is not a claim of successful resolution; forwarded/cached/retried/in-progress statuses are explicit. Unsupported statuses are discarded.
- Credentials, sessions and DNS client identities are never included in the dashboard projection.

## Release acceptance
- Backend: 218 tests and 92 subtests passed, including 18 Pi-hole tests.
- Native-renderer/frontend/wiring: 13 tests passed; networking JavaScript: one test passed.
- Strict RED/GREEN exercised backend, partial states, removed summary/WAN, and secret-reference wiring.
- Source warning and per-device real warnings retained; the redundant NETWORK OVERVIEW header, summary counters and WAN panel are removed. UDM SE prominence, infrastructure histories and expanded clients remain.
- TOML parses; Compose validates with dummy values only. Named telemetry-history and geoip-city volumes remain untouched.
- Saved Komodo stack environment updated by existing authorized browser operator session using a narrow UpdateStack environment edit; protected reference read back before deployment. No collector privilege changes. Broad Resource Sync was not run, avoiding unrelated resource changes.

Runtime evidence is collected separately in `pihole-live-qa/` (not committed, as it contains private DNS history). The earlier NETWORKING-LOWER-QA.md describes the historical blocked release, not the current integration.
