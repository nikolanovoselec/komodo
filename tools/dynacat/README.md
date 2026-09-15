# Dynacat workload overview

The private `workload-summary` sidecar joins Komodo read responses and returns a
small allowlisted JSON projection to Dynacat. It has no published port, Docker
socket, SSH credentials, host metrics mounts, or write API route. It runs as an
unprivileged user with a read-only filesystem and digest-pinned Python image.

## Filtering and failures

- Hosts are hidden only when Komodo explicitly reports `Disabled`.
- Stacks are hidden when their host is disabled or they carry the live `disabled`
  tag ID (resolved through `ListTags`, not a hardcoded ID).
- Containers are hidden by exact `(server_id, container_name)` membership in a
  disabled stack's `GetStack.info.deployed_services`. Prefix matching is forbidden.
  Unknown/unmanaged containers remain visible, including stopped ones.
- Template flag is not a disable flag: deployed running template stacks remain.
- Unassigned stack definitions stay visible in a separate expandable section; they
  are not counted as runtime stack incidents. Enabled assigned down, stopped,
  unknown and unhealthy workloads remain runtime issues.
  A running Docker container whose status includes `unhealthy` is a problem.
- Failed upstream reads return 503, not stale green counts or an empty success.
- CPU percentages and RAM units are parsed numerically before sorting. Missing
  stats are omitted from rankings, not substituted with zero. Docker CPU can exceed
  100% on multi-core hosts. Network/block-I/O counters are not displayed as rates.

Only `ListServers`, `ListStacks`, `ListTags`, `ListAllDockerContainers(limit=0)` and
`GetStack` are called. `GetStack` includes configuration; it is never logged,
persisted, or forwarded. Only deployed container names are retained for filtering.
Credentials are protected Komodo environment variables shared with the dashboard.
The summary cache lasts 5 seconds; operational widgets refresh one second after
completion of their previous request while the page is visible (`cache: 1s` and
`update-interval: 1s`). This is a one-second UI polling interval, not a promise of
new measurements every second. The shared single-flight collector cache keeps the
four widget reads from multiplying expensive integration collections. They read
`/current`, which serves the last sample without waiting for background upstream
I/O. Snapshot state/age is displayed; data expires 30 seconds from collection start.
Cold start, expiry or collection failure returns 503 and the widget's explicit
unavailable branch—not zero/healthy counts. Failed attempts are throttled for five
seconds. `/summary` and `/health` still wait for the shared attempt, without holding
the reader lock. The age limit describes the collection snapshot, not RRD/ZFS/GitHub
measurement age; those independently cached sources retain their own cadences.
PVE current CPU/RAM samples originate from pvestatd approximately every 10 seconds.
Native one-minute RRD graph samples and ZFS/storage reads are cached for 60 seconds;
GitHub retains its ten-minute cache. Faster polling does not invent graph samples.
Native Dynacat polling pauses hidden documents and prevents overlapping widget reads;
the collector serializes cache refreshes and throttles failed retries for 5 seconds.

Run regression tests: `python3 -m unittest discover -s tools/dynacat/adapter -v`.
Stage the actual two-service Compose application with isolated names/assets/ports,
then inspect desktop/mobile screenshots before pushing. Bump the Compose revision
label for tracked config changes so `BatchDeployStackIfChanged` redeploys them.

## Proxmox Resources / VM-LXC overview

Dynacat 3.0.0 has no native Proxmox widget. Its native `server-stats` expects a
Dynacat sysinfo endpoint, not Proxmox, and does not supply the requested network
history or VM/LXC overview. A native `custom-api` template can render real PVE JSON:

- `/api2/json/cluster/resources?type=vm`: compact VM/LXC current state/CPU/RAM.
- `/api2/json/nodes/{node}/status`: node resource cards.
- `/api2/json/nodes/{node}/rrddata`: node resource/network history.
- `/api2/json/nodes/{node}/{qemu|lxc}/{vmid}/rrddata`: guest history.
- `/api2/json/nodes/{node}/storage/{storage}/status`: datastore capacity.

Required: reachable HTTPS endpoint, trusted CA and dedicated PVE monitoring user.
The deployed `dynacat@pam!dynacat` token inherits its dedicated user permissions
(`privsep=0`); both effective permission sets are audit-only. If enabling token
privilege separation later, assign audit permissions to BOTH the user and token:

| Privilege | Scope (propagate when covering children) |
| --- | --- |
| `Sys.Audit` | `/nodes/<node>` for each selected node |
| `VM.Audit` | `/vms/<vmid>`, or `/vms` for all VM/LXC guests |
| `Datastore.Audit` | `/storage/<storage-id>`, or `/storage` for all |

`PVEAuditor` on `/` is a broader read-only alternative, not the minimum.
Do not grant power, console, configuration, allocation or guest-agent privileges.
Header: `Authorization: PVEAPIToken=<user>@<realm>!<token-id>=<secret>`.
Inject via protected Komodo variables only. No root/SSH keys in containers.
Cluster resource responses are permission-filtered; HTTP 200 alone is insufficient.

Do not present cumulative netin/netout/diskread/diskwrite counters as rates. Use
actual RRD rates or measured deltas. Guest filesystem usage may be unavailable:
virtual disk capacity is not actual filesystem consumption. Do not double-count
shared storage. No Proxmox metrics are fabricated. Tools-to-PVE TCP 8006 is now
reachable on all three cluster nodes. The user-provided
DYNACAT_PROXMOX_TOKEN_ID and DYNACAT_PROXMOX_SECRET variables are wired to
Compose without modifying the token ID. TLS uses the public cluster CA from
`/etc/pve/pve-root-ca.pem`, read over existing trusted SSH, never a private key.
The legacy cluster CA lacks a keyUsage extension. The PVE-only TLS context clears
`VERIFY_X509_STRICT` (enabled by Python 3.13), preserving `CERT_REQUIRED`, hostname
verification and all other verification flags. This relaxes RFC certificate-profile
strictness, not chain trust; no unverified context or global TLS override is used.
Replace the legacy CA through normal cluster certificate maintenance to remove
this compatibility exception in the future.
Node/guest-count reads fail independently from Komodo. Genuine one-hour CPU RRD
history and the latest RRD-average ingress/egress rates are read through a narrow
node-derived GET allowlist. Optional RRD failure never erases current resources.
The central Resources cards are ordered proxmox-i, proxmox-ii, proxmox-iii.
The cards show ZFS storage only; root-filesystem gauges are intentionally omitted.
Physical ZFS pool allocation (alloc/size/free) is read from each node’s
`/nodes/{node}/disks/zfs`; the existing audit token supports this without any new
privileges. Root filesystem usage and ZFS pool allocation overlap and must never
be summed. Pool capacity does not identify rotational HDD versus SSD media.
If the pool endpoint is unavailable, an explicitly labeled ZFS-backed-storage
fallback joins `/storage` and `/nodes/{node}/storage`, choosing one shallowest
active dataset per pool rather than summing aliases or child datasets. Missing
readings remain unavailable, not zero. No storage configuration is exposed.
Compact Proxmox guest cards below show running VM/LXC resources with stopped
guests in a separate disclosure. VM RAM is explicitly host-accounted, not guest
OS available memory. QEMU host RAM can exceed configured guest RAM due to
emulator overhead; preserve that real reading and label its configured denominator.
VM filesystem usage is unavailable; separately labeled allocated disk capacity
is informational and is never graphed as used space.
Guest stopped status is not treated as a disable policy. Komodo remains the Docker
container/stack source only. Top CPU/RAM entries link to the exact container route
`/servers/{server_id}/container/{container_name}`; disk rankings link to host detail.
Workload attention precedes Top 5 in document order.

Network graphs use real per-direction RRD byte/second rates with a shared scale
per node, timestamp-ordered one-minute buckets and visible gaps for missing data.
The legend separates receive (solid blue) from transmit (dashed green), with actual
history duration and scale. No cumulative counters are presented as rates.

The right rail contains open `renovate[bot]` PRs for nikolanovoselec/komodo. The
server-only `DYNACAT_GITHUB_TOKEN` comes from protected Komodo variables into the
private adapter, never the frontend. HTTPS GET requests are hardcoded, redirect
blocked, paginated at most five pages and cached for ten minutes. Counts represent
actually returned PRs with an explicit truncated flag. API failures are unavailable,
not empty-green. The repository was also verified readable anonymously; no broad
personal OAuth credential is copied or needed. Mounted volumes/news are removed.
 Disk top 5 ranks enabled reporting Komodo hosts by aggregate
filesystem capacity percent, not physical disks, per-container consumption or I/O.

Diagnostic classification (2026-09-15): all four `nextcloud_*` definitions have no
server/swarm assignment and old deployment metadata, but no disabled tag. No
matching Nextcloud server/container exists in the managed inventory. Middleware
`traefik` is a real exited-128 legacy unmanaged container (Compose project
`traefik`, `/data/compose/34`), finished 2025-03-27. Docker reports inability to
create `/mnt/configs/traefik/acme.json` due to permission denied. Its
`unless-stopped` policy and absent retirement evidence mean it remains actionable;
this dashboard change neither restarts nor deletes it.

References: https://pve.proxmox.com/pve-docs/api-viewer/ and
https://pve.proxmox.com/pve-docs/chapter-pveum.html .

## Verified VM guest fallback

The six running VM identities are explicitly bound in `adapter/vm_metrics.py` by
VMID plus exact name guard to immutable Komodo server ID and verified endpoint.
PVE net0 MACs were independently matched to each guest's IP/interface. Openclaw
was verified locally on the Hermes execution host; other guests via existing
trusted read-only SSH. No runtime SSH credentials or additional PVE permissions
were introduced. Re-audit these bindings after VM recreation or IP reassignment.

For those VMs only, fresh reporting enabled Komodo guests supply RAM and aggregate
filesystem usage, labeled per card. PVE host-accounted RAM is retained separately.
LXC values, all physical node values, guest inventory/state/node and CPU stay PVE.
Unmatched/offline/disabled/stale sources never substitute zero or invented readings.
Shared/multiple guest mounts may overlap; aggregate usage is not a virtual disk
allocation or a physical ZFS pool measurement.


## Exact resource navigation and live header

Node cards and every running/stopped VM/LXC card use the installed Proxmox
History.js v1 encoded resource ID and resource-specific Summary tab. Public origin
is `https://proxmox.graymatter.ch`; no API credentials or internal endpoint strings
are placed in navigation URLs. Docker CPU/RAM and attention entries use deployed
Komodo 2.3.2's `/servers/{server_id}/container/{encoded_name}` route.
Disk-ranked host links use the same audited VM bindings plus LXC 101/128 bindings
in `navigation.py`. Those LXC MAC/IP pairs were checked through `pct config` and
`pct exec ... ip -j address show`: 101 `bc:24:11:ef:65:3b` / `192.168.2.205`,
128 `bc:24:11:9e:fe:2b` / `192.168.3.12`. Identity mismatches retain telemetry but
show an unavailable exact Proxmox link rather than guessing or redirecting Komodo.
All current ranked hosts have verified mappings.

The landing Control plane/Bookmarks and Critical releases widgets are removed;
Directory, Media Ops and News are preserved. Native live Clock (browser-local date
plus Bern/New York IANA zones) and Bern Weather lead the right rail directly above
Renovate. The desktop rail is 286px (30% wider than the previous 220px). Below
1100px it stacks after telemetry, with date/clocks, weather, Renovate in that order.
No date, timezone offset or weather is hardcoded; the former top-strip wrapper is removed.
`command-center.js` uses the native `dynacat:widget-updated` event to preserve
open disclosures and focused links across refreshes; it adds no polling.

## Guest resource matrix and independent physical refresh

The workload overview is a resource matrix, not a grid of boxed guest cards. Each
linked row shares CPU/RAM/disk bullet-meter columns, with identity/node/type on
the left and per-metric sources on the right. Node/VMID, measured values, RAM
denominator and disk usage remain visible. Names are 12px, numeric readings 12px,
and sources/capacity text 10px. Rows are 48px on desktop/tablet; below 680px widget
width they stack to approximately 81px. Stopped disclosure/links retain 44px touch
targets. One row per guest is deliberately a different diagram: individual rows
are smaller, but the whole desktop matrix is taller than the former 3-column grid.

Physical node visuals are unchanged. They now read `/pve-current`, an independent
nonblocking bounded-age PVE snapshot, so slow/failing Komodo or GitHub reads cannot
hold back physical-node updates. General `/current` and `/pve-current` share one
PVE singleflight/cache (five seconds between completed attempts), without a second
upstream polling loop. Optional RRD/ZFS caches remain 60 seconds. Failures clear
old healthy readings; snapshots expire 30 seconds from collection start.

Live diagnosis measured UI updates around 1.02s, PVE publications around 6s, and
actual upstream node changes around 10s (uptime advances in 10-second steps). RRD
graphs contain 60-second buckets. `fetched_at` is explicitly collection time, not
a source measurement timestamp: polling cannot invent 1Hz PVE measurements.

Run `qa_compact.py URL OUTPUT` for four-viewport light/dark matrix alignment and
metric preservation; use `--baseline` before future changes for bounds/screenshots.

## Unified Cluster Workloads / Docker

The former standalone Docker Hosts widget is merged into the guest resource
matrix. Physical-node cards, Top Consumers and the right rail are unchanged.
`workload_docker.enrich` joins only the existing audited VM/LXC mappings, exact
PVE type/ID/name and immutable Komodo server ID/address. Each matched row adds
running/total containers, stopped/other and unhealthy counts, summed running-
container CPU/RAM, and an expandable exact-linked inventory. CPU may exceed 100%;
RAM is container accounting, never substituted for host/guest memory. Expanded
rows expose measured coverage. Source freshness must be strictly under 30s.
Disabled Docker resources stay excluded. Missing Docker inventory is not zero
containers or proof of no daemon. Unmatched hosts and unassigned definitions
remain separate disclosures; assigned stack problems stay with their machine.
All PVE inventory/state/CPU and prior VM-metric fallback behavior is retained.
`qa_workload_merge.py` verifies actual expansion/focus across polling and
light/dark desktop/tablet/mobile rendering. Fixtures test disabled, stale,
identity-mismatch, missing-stat and actionable-failure cases.

## Native Media Ops

`/media` is the native, theme-aware Media page with scoped styles; `/media-ops`
redirects to it. All theme definitions remain unchanged. `adapter/media.py`
provides fixed read-only `/media-current`, `/media-library` and `/media-arr`
projections. No media control/write endpoint is exposed. The sidecar retains its
unprivileged, read-only, private-network-only deployment.

- Komodo supplies exact Plex, Emby and Jellyfin container identities, CPU and RAM.
  Jellyfin remains explicitly visible because this page names all three servers;
  its authoritative disabled tag is labeled separately from its exited state.
- All three use host networking. Docker `net_io=0B / 0B` is not a measured idle
  per-app bandwidth value. The page explicitly marks per-app traffic unavailable.
  Separate host traffic shows Periphery's received/transmitted bytes from the last
  declared polling interval across all interfaces, **not bytes/second** and not
  Plex-only traffic. `refresh_ts` must be younger than 30 seconds.
  Verified implementation: Komodo v2.3.2 `bin/periphery/src/stats/mod.rs` sums
  sysinfo `received()` / `transmitted()` (since the previous network refresh).
- Sonarr/Radarr reuse their existing protected Komodo variables in the sidecar.
  History uses eventType=3 (completed imports), queues retain bounded pagination
  and an explicit truncated flag. Failed reads are not displayed as empty queues.
- Plex uses the user-provisioned protected `DYNACAT_PLEX_TOKEN`, wired through
  `tools_dynacat` TOML and the collector's Compose environment only. It is never
  injected into the browser or copied from a browser session. Authenticated
  staging reads verified all four libraries, actual playback sessions and 16
  real latest-media posters. Missing/invalid credentials remain explicit errors.
- Plex library requests ask for actual `type=4` episode items sorted by `addedAt`
  (not season-level recentlyAdded records); movie requests use `type=1`. Section
  totals count top-level library items (shows, movies, artists), not episodes for
  TV totals. Playback bandwidth is Plex's session reservation, not measured NIC
  throughput. Sources/cache cadence are explicitly labeled.
- Until Plex access is configured, the separate **Just landed** gallery presents
  verified Arr imports, explicitly not Plex library membership. IMDb links use
  only upstream identifiers validated as `tt` plus 7–10 digits.
- Poster bytes are fetched server-side from fixed Plex/Radarr paths or an exact
  HTTPS TVDB artwork origin/path allowlist. Redirects, arbitrary URLs, oversized
  payloads and non-JPEG data are rejected. Browsers receive bounded JPEG data URIs,
  never token-bearing URLs or upstream credentials. Missing artwork remains a
  labeled placeholder. Gallery/image work cannot block 1s resource presentation.
- Independent demand-driven caches: sessions/resources 5s, Arr 30s, library/artwork
  5m. Failures invalidate prior snapshots and stale data expires. Native Dynacat
  owns polling (1s current, 10s delivery/gallery), pauses hidden pages and prevents
  overlap. Media-only JS preserves disclosure/focus/scroll across replacement.

Run `python3 -m unittest discover -s tools/dynacat/adapter -q` and
`dynacat-qa-venv/bin/python tools/dynacat/qa_media.py BASE_URL OUTPUT_DIRECTORY`.
The browser regression uses the actual app/upstreams, verifies loaded images,
1s completion cadence, focus/disclosure retention, two contrasting persistent
native themes, and four viewport widths; it never serves synthetic telemetry.

## Navigation, launcher and Bern calendar

The visible navigation is **Hardware & Workloads**, **Media**, and
**Endpoints & Services**. Fixed hidden aliases preserve `/command-center`,
`/media-ops`, `/directory`, and `/news` bookmarks. The launcher preserves all 86
original links across eight categories and all three original news feeds in its
secondary News desk, with client-local search and category filters. Start was
inspected read-only as the visual reference; no endpoint credentials are copied.

The native Clock widget uses Europe/Zurich, Europe/London, America/Los_Angeles,
and America/New_York in Bern/London/San Francisco/New York order. The monthly Bern
calendar is timezone-explicit and Monday-first with no agenda/holiday claims.
Upstream Dynacat's calendar uses browser-local Date and has no timezone field, so
this scoped native-style month grid uses Intl Europe/Zurich instead. It was tested
with a Pacific/Kiritimati browser timezone to prove the Bern date stays correct.
Weather and Renovate remain below it, retaining the existing rail width.

Workloads has no metric-sources column; per-machine PVE source information is
retained in link tooltips and the scope note. Expanded Docker rows have an explicit
sticky Hide containers button, an expanded-header hint, native keyboard summary
and synchronized aria-expanded/aria-controls. Empty unmatched/unassigned groups
are omitted independently; unknown exception data retains an error state. Issue
counts live at the title's right edge, vertically centered; zero uses normal text,
positive counts alone use the theme's negative color.

qBittorrent uses fixed transfer/info and downloading-filter GETs through its
existing LAN access policy, verified from the collector. No login, controls or
settings writes are used. Transfer speeds are measured API rates; Plex bandwidth
is separately labeled reserved capacity with reported-session coverage, including
partial coverage rather than silently treating unreported streams as zero.

## Browser-local theme compatibility

The public URL's native theme POST returned HTTP 403 with `cross-origin request
rejected`, while the identical LAN browser action returned 200. Dynacat's
same-origin middleware compares the browser Origin host with the forwarded Host;
this deployment's proxy path does not preserve a matching Host. This is unrelated
to editor permissions or filesystem writes: upstream `theme.go` only sets a cookie
and returns preset CSS. Do not weaken that middleware or enable the editor.

`local-theme.js` uses the existing non-HttpOnly `theme` cookie and Dynacat's native
GET page rendering to obtain the selected preset CSS, without executing returned
scripts. It stores the same `{key, css, scheme}` under `dynacat-theme` used by
upstream's before-paint restore and cross-tab synchronization. Only the theme picker
is intercepted; widgets, controls, config and write APIs are untouched. A failed
read restores the previous cookie and leaves the picker retryable, with a useful
error message. No preset CSS is duplicated or removed. Local cookie reconciliation
also avoids the native stale-cookie POST on reload.

Browser regression (with Playwright installed):
`python qa_themes.py http://192.168.2.72:8080 /tmp/dynacat-theme` from this directory.
The regression forwards actual theme POSTs with the observed Origin mismatch;
it does not fake the error response. `--staged` loads only the local candidate
asset/head before deployment. Confirm the public URL separately with its existing
Cloudflare Access browser session. Runtime and config remain Git-managed.
