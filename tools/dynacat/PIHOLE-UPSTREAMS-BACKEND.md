# Pi-hole upstream DNS and interval bars

## Sources and live verification

Official v6 specification: https://github.com/pi-hole/FTL/blob/master/src/api/docs/content/specs/config.yaml (`get_config_elem`, element `dns/upstreams`). Authenticated read-only `GET /api/config/dns/upstreams` returns `config.dns.upstreams`. Never fetch the entire configuration. No stats/upstreams fallback: configured forwarders and observed traffic are different facts.

Verified both endpoints from `tools_dynacat_workload_summary` on 192.168.2.72, using existing pinned transport and server-only `PIHOLE_API_KEY`. Both returned exactly `8.8.8.8`, `8.8.4.4`, `1.1.1.1`, `1.0.0.1`. Source omitted ports, so none are invented. Literal configured ports (`127.0.0.1#5335`) and IPv6 strings remain unchanged. These are configuration, not resolver health checks or inferred provider names.

Sanitized captured-real fixture: `adapter/fixtures/pihole-upstreams-history.json`, capture epoch 1789548418. Only names, upstream subset and last-window timestamp/total/blocked bins retained. No sessions, credentials, clients, domains or other configuration. Candidate backend was additionally executed in memory inside the existing collector runtime (no filesystem replacement or deployment): both upstream reads and combined three-bin history succeeded.

## Additive JSON contract

Each `instances[]` entry includes:

- `configured_upstreams`: list of exact source strings; `null` on unavailable/invalid source. Empty list means successfully read empty configuration.
- `upstreams_available`: boolean, independent of summary availability.
- `upstreams_error`: null on success, fixed sanitized explanation on failure.
- `upstreams_truncated`: true when only the first 16 entries are returned.

Each string is limited to 256 printable characters; malformed lists fail closed. Upstream endpoint failures never discard otherwise valid summary/history. Existing summary partial semantics remain unchanged. Existing certificate pin verification, response-size limits, session logout and cache remain unchanged.

`query_history` adds `max_total_count`: largest combined permitted+blocked count among complete source bins. Each actual `points[]` adds `label` (HH:MM UTC), `permitted_percent`, `blocked_percent`, with percentages calculated against that common total maximum for stacked bars. Missing/invalid combined points retain null counts and null percentages; actual zero bins get zero percentages. No timestamps or bins are synthesized. Existing `max_count`, paths, area paths, timestamps and interval/window fields remain compatible.

## Verification

Strict RED/GREEN slices covered real-fixture upstream projection, upstream-only failures, bounded literal forwarding, unavailable instances and common-total interval bars. Regression coverage includes null/zero/empty history, TLS pin enforcement, session logout and caching. Full adapter suite: 233 passed plus 92 subtests passed. `git diff --check` passed. No commit, deployment or Pi-hole configuration write performed.
