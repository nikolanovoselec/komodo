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
- Enabled down, stopped, unknown, unassigned and unhealthy workloads stay visible.
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

## Proxmox Resources / VM-LXC overview: pending credential

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
shared storage. No Proxmox metrics are fabricated or deployed by this change.

References: https://pve.proxmox.com/pve-docs/api-viewer/ and
https://pve.proxmox.com/pve-docs/chapter-pveum.html .
