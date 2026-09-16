# Pi-hole continuous activity chart

Supersedes PIHOLE-REDESIGN-QA.md's stacked interval bars. Baseline ac759e848db4a6751b233babacfc8a1b4528a560 was verified deployed before editing; tracked checkout clean, prior untracked evidence preserved.

## Acceptance and design
- [x] Pi-hole remains first, full width, configured per-instance upstreams unchanged.
- [x] ONE common 30-minute plot, permitted and blocked lines with distinct translucent fills, no bars/tiles.
- [x] Live Proxmox reference captured and inspected before implementation: compact node heading, inline counter row, shared activity section and restrained frame.
- [x] Counters compacted to 24px desktop / 22px mobile; activity now full-width beneath rather than beside counters.
- [x] Reuse actual collector paths verbatim (600×140), shared max_count scale, start/end UTC labels; preserve entire wall-clock 1800-second viewport and blank unsampled ends.
- [x] No fabricated measurements, interpolation samples, smoothing, backfill or gap bridges. Permitted means total minus blocked, not proven successful resolutions.
- [x] RED: native chart-count expectation failed 0 != 1 before markup/styles; GREEN native behavior and computed layout passed.
- [x] Native changed-fixture refresh verifies independent M/Z gap subpaths and genuine zero-height zero values; unavailable history retained.
- [x] Same captured-real baseline/candidate in native renderer, 1600/390 dark/light. No overflow; mobile touch refresh drift zero. Actual-data screenshots separate from explicit synthetic gap tests.
- [ ] Deployment exact commit, HTTP, runtime assets and Komodo state verified after push.

## Source resolution
Official v6 /api/history provides actual 600-second bins. FTL.h OVERTIME_INTERVAL=600; database history also uses 600 seconds and offers from/until, no finer interval parameter. Existing protected pinned transport and backend remain unchanged. Straight lines connect actual adjacent bins; this is not a claim of higher-frequency measurement. Each missing interval splits the source line/area paths. Blank ends are intentionally not extrapolated.

Sources: https://github.com/pi-hole/FTL/blob/master/src/api/docs/content/specs/history.yaml ; https://github.com/pi-hole/FTL/blob/master/src/FTL.h ; https://github.com/pi-hole/FTL/blob/master/src/api/stats_database.c

## Evidence
`pihole-redesign-qa/continuous-{before,baseline,candidate,live}-{dark,light}-{1600,390}-{page,pihole}.png`; JSON reports beside them. `pihole-continuous-qa/nodes-reference.png`; fresh deployed archive `pihole-continuous-qa/backup/deployed.tgz`, tar integrity verified. Captured-real source `/tmp/network-query-current.json` reused unchanged across native baseline/candidate.

Measured candidate panel 391.56px desktop vs 360.09 baseline; 574.59px mobile vs 598.59 baseline. Full-width chart costs 31.47px desktop but saves 24px mobile. Infrastructure section unchanged 1060.70px / 2057.03px.

Validation: 39 scoped Python/native tests passed; networking JS regression passed. Native renderer validates actual production template. Renderer revision continuous-54; collector label remains cockpit-53, history volumes unchanged. Before collector ID a15a9c2ed2e0bca6956c31fa7e349c4a60aef4aa35d676a55c15f38ce2bedbb0, started 2026-09-16T09:03:43.028546041Z.
