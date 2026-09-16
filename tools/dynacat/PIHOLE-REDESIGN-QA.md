# Pi-hole cockpit redesign acceptance

Supersedes the lower-page query-line layout in NETWORKING-QUERY-QA.md. Pi-hole is first, full-width, ahead of unchanged infrastructure.

## Design evidence
Live baseline inspected at 1600/390, dark/light before designing. Weaknesses: buried after seven devices, three weak equally weighted counters, long legend wrapping on mobile, oversized sparse line drawing, no resolver configuration. Replaced with primary total/blocked/rate hierarchy, secondary honestly summed blocklist, compact actual ten-minute stacked bars, and two explicit per-instance configured-forwarder rows. Green permitted and rose blocked shading remains translucent. Tooltip defines permitted as total minus blocked, not guaranteed successful resolutions.

Captured-real native baseline/candidate use identical source `/tmp/network-query-current.json` and native renderer. Desktop panel 492.969 → 360.094px; phone 526.281 → 598.594px (adds two upstream rows and blocked percentage, not claimed smaller). Infrastructure unchanged: 1060.703px desktop / 2057.031px mobile. All four layouts have no horizontal overflow. Mobile touch swipe settles and retains exact scroll position through refresh.

## Acceptance
- [x] First full-width Pi-hole; UDM SE and peripheral grouping preserved.
- [x] Actual protected/pinned upstream source, per-instance configuration labels, no invented ports.
- [x] Exact aggregate source counts and three actual 600-second bins; null unavailable, real zero zero-height.
- [x] Strict RED/GREEN: source projection, order, computed grid/legend layout, zero-height regression.
- [x] 33 Pi-hole backend tests; five native tests; networking JS regression.
- [x] Captured-real 1600/390 dark/light page/widget screenshots reviewed.
- [ ] Production deployment and health verified after commit.

Run `qa_pihole_native.py` for captured-native matrix and `qa_pihole_redesign.py URL live` for production. Evidence at repository-root `pihole-redesign-qa/{before,baseline,candidate,live}-{dark,light}-{1600,390}-{page,pihole}.png` and JSON reports. Fresh secret-free deployed config/assets archive `pihole-redesign-qa/backup/deployed.tgz`, production baseline 7900c2a60826f525638e918646f82503eaf10aa8. QA containers removed; pre-existing stopped containers preserved.

Backend endpoint/schema detail: PIHOLE-UPSTREAMS-BACKEND.md. No Pi-hole configuration writes, DNS query records, credentials or SIDs exported. Persistent volumes unchanged. Both collector and renderer revision `construct-pihole-cockpit-53` because backend changed.
