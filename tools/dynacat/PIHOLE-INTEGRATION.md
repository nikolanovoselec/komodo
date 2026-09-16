# Pi-hole combined query history

The Networking page retains infrastructure and makes Pi-hole full width. Connected clients and both DNS domain lists were removed by the superseding user request.

Server-side collector uses existing protected PIHOLE_API_KEY and pinned HTTPS for both v6 instances. Read-only `/api/stats/summary` supplies total/blocked counters and gravity domains (sum, not deduplicated). `/api/history` supplies `history[].timestamp`, `total`, `blocked`; actual source bins are 600 seconds apart. No `/api/queries` requests or DNS domain/client export in the Pi-hole projection.

Last-30-minute query diagram aligns exact provider timestamps and sums both instances. Permitted = total minus blocked, not guaranteed successful resolution. Shared counts scale, distinct shaded series, queries per 10 minutes, UTC endpoints. It is activity per interval, not a cumulative running counter. Only actual bins within the window are drawn; no synthetic backfill. A missing/invalid source bin makes the combined point null, never zero or a misleading single-instance total. Null points and >600-second gaps break line and area paths independently. Counters still sum available instances and label partial state.

Security remains unchanged: leaf SHA256 pins verified before credential/session transmission, bounded response size and inactivity timeout, server-only credentials, logout in finally, single-flight cache. No Pi-hole settings changes. Named volumes preserved. Collector and renderer revisions advance through Git/Komodo only.

Verification: strict RED/GREEN for aggregation/privacy, missing/null gaps, official endpoint replacement and time labels; native RED/GREEN for removal/full-width/chart. See NETWORKING-QUERY-QA.md. Captured-real artifacts remain untracked.
