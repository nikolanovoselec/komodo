# Pi-hole native Proxmox chart match and precollected backend

Supersedes the continuous-area interpretation. Tracked baseline was clean at origin/main 4f043938; existing untracked evidence and other checkout preserved. Live deployment backup archived locally before edits.

## Acceptance verified before release
- One aggregate Pi-hole panel above infrastructure; counters and per-instance configured upstream IPs retained.
- Actual live reference is **line-only**, not filled: `.pve-network`, `.pve-netgraph`, `.pve-gridline`, `.pve-rx`, `.pve-tx`, `.pve-netaxis`, `.pve-rx-label`, `.pve-tx-label` reused directly.
- Shared 100×30 SVG viewport, 38px rendered height, 6px top margin, three horizontal gridlines. Solid permitted and dashed blocked (4 2), 1.4px non-scaling strokes, same theme tokens. Native axis beneath plot, values beneath axis. Ten-minute bin timestamp/units explicitly labeled; no RX/TX or bandwidth semantics.
- Full-width outer panel; compact counter block beside node-proportioned plot on desktop; stacked on touch mobile. No per-instance duplicate charts.
- Original 600×140 collector line paths retained verbatim under an affine scale into native viewport. Null/gap segments and unsampled ends unchanged. No synthetic finer samples.
- Strict native RED comparison failed all four baseline theme/viewport cases before production edits. GREEN compares computed strokes, fills, geometry, typography, axis and label placement at 1600/390 dark/light; no overflow/browser errors. Screenshots visually reviewed, mobile touch across polling drift <2px.
- Native changed-fixture gap/zero/unavailable tests pass. 250 Python tests and 92 subtests pass; networking JS regression passes.
- Pi-hole joins lifecycle warmers independently of requests. Reads return cached projection without waiting for upstream; singleflight refresh. Atomic bounded public snapshot `/history/pihole.json` in existing telemetry volume. Restart reload preserves collection-start age; stale/partial history explicitly labeled, expired counters unavailable. No domain query lists persisted or fetched.
- Backend test coverage: no-view collection, nonblocking cold/blocked refresh, singleflight, bounded persistence/reload, corruption rejection and truthful timestamps. Collector revision explicitly bumped for newly authorized backend scope.

Deployment verified: implementation `4158b3bf02cc8570e7670fe27cd9e67f179c5a45` (rebased over unrelated Prowlarr Renovate merge). Komodo `deployed_hash=4158b3bf`, `running(5)`, no remote errors; collector and GeoIP healthy. Frontend revision native-55 and collector precollected-55 are running. Networking and Hardware HTTP 200. Served asset bytes match repository SHA256; networking uses digest URL e65b846a36c7, native command-center stylesheet uses Dynacat-generated file timestamp cache version.

Live native comparison also passes all four cases. Live mobile touch-refresh drift is exactly 0px in both themes. Deployed chart is 489.34×38 desktop and 322×38 mobile. Backend snapshot advanced from 1789551481.6957598 to 1789551493.4797773 without an endpoint request; `/network-current` returned in 15.07ms inside collector with cached available Pi-hole data and three real bins. Persisted public snapshot is 1780 bytes. A fresh Snapshot instance in the production container reloaded identical history; this verifies restart loading without an unnecessary second production container restart. Existing media/unifi/workload history files remain present. Actual upstream collection completion advances frequently; ten-minute source bin timestamps correctly do not advance every poll.

Evidence: `pihole-native-qa/{before,candidate,live}-report.json`, computed measurements and native reference/candidate/live chart/cards/side-by-side screenshots. Source is captured real production JSON; synthetic gap tests are separate. `qa_pihole_native_match.py` reruns the native comparison.
