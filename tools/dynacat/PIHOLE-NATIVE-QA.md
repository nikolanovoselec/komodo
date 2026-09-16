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

Evidence: `pihole-native-qa/{before,candidate}-report.json`, computed measurements and native reference/candidate chart/cards/side-by-side screenshots. Source is captured real production JSON; synthetic gap tests are separate. `qa_pihole_native_match.py` reruns the native comparison. Deployment verification is recorded separately after push; staging success alone is not deployment.
