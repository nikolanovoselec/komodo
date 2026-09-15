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
The response cache lasts 15 seconds; the UI refreshes every 30 seconds.

Run regression tests: `python3 -m unittest discover -s tools/dynacat/adapter -v`.
Stage the actual two-service Compose application with isolated names/assets/ports,
then inspect desktop/mobile screenshots before pushing. Bump the Compose revision
label for tracked config changes so `BatchDeployStackIfChanged` redeploys them.

## Proxmox Resources / VM-LXC overview: wired, network blocked

Dynacat 3.0.0 has no native Proxmox widget. Its native `server-stats` expects a
Dynacat sysinfo endpoint, not Proxmox, and does not supply the requested network
history or VM/LXC overview. A native `custom-api` template can render real PVE JSON:

- `/api2/json/cluster/resources?type=vm`: compact VM/LXC current state/CPU/RAM.
- `/api2/json/nodes/{node}/status`: node resource cards.
- `/api2/json/nodes/{node}/rrddata`: node resource/network history.
- `/api2/json/nodes/{node}/{qemu|lxc}/{vmid}/rrddata`: guest history.
- `/api2/json/nodes/{node}/storage/{storage}/status`: datastore capacity.

Required: reachable HTTPS endpoint, trusted CA, dedicated PVE monitoring user and
privilege-separated API token. Assign audit permissions to BOTH the user and token:

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
shared storage. No Proxmox metrics are fabricated. The collector and template are deployed, but
tools-to-PVE TCP 8006 times out; authentication, permission coverage and live
rendering remain unverified until the network allows it. The user-provided
DYNACAT_PROXMOX_TOKEN_ID and DYNACAT_PROXMOX_SECRET variables are wired to
Compose without modifying the token ID. TLS uses the public cluster CA from
`/etc/pve/pve-root-ca.pem`, read over existing trusted SSH, never a private key.
Node/guest-count reads fail independently from Komodo. Network history remains
unimplemented. Disk top 5 ranks enabled reporting Komodo hosts by aggregate
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
