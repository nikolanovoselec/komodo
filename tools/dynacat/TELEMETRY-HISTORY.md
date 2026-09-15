# Thirty-minute telemetry history

## Deployment and storage

The collector mounts the named `telemetry-history` volume at `/history`, with `WORKLOAD_HISTORY_PATH=/history/workloads.sqlite` and `MEDIA_HISTORY_PATH=/history/media.sqlite`. The pinned collector image creates `/history` owned by UID/GID 65534 before Docker initializes the volume. The collector remains non-root with a read-only root filesystem. No one-shot initialization service is added to the Komodo application stack. SQLite is Python stdlib.

`telemetry-history.css` is loaded with a content-hashed URL. Application and collector revision labels are changed through the tracked Compose release. The independently configured UniFi token is injected only into the collector; this does not establish gateway reachability or implement the Networking page.

## Metric semantics

All telemetry history windows cover wall-clock last 1800 seconds. Missing samples and collection pauses remain gaps. Node CPU uses separate segments instead of bridging missing buckets. Network lines retain native rates and shared scales.

Read-only live PVE probes verified actual guest RRD minute samples. All nine running guests provided CPU history; three LXCs also provided memory and used-filesystem history. QEMU disk=0 is not used as proof of empty guest storage. Six audited Periphery VM bindings collect real, source-timestamped RAM and disk-used samples; no guest-OS backfill was verified, so these histories accumulate from deployment onward. Identity includes guest type/ID and the verified immutable server binding. Existing links, disclosures and current readings remain.

Percentage scales are explicit; genuine values above 100% increase the scale rather than being clipped. Disk I/O and allocated capacity are never substituted for used-disk history. Source provenance remains available in graph tooltips. Collection only grows while the existing collector is invoked; unattended periods remain gaps.

## Failure isolation

Optional guest RRD refreshes use a separate bounded background cache, with at most two workers, no pending-work queue, per-path single-flight and a 60-second success/error cooldown. They do not hold the physical-node cache lock or block current workload publication. Stopped guests do not schedule history reads.

Workload SQLite operations use a 50 ms timeout and a locked, timestamp-pruned memory fallback on runtime storage errors. Persistence is marked unavailable without failing current telemetry. Media persistence also exposes unavailable storage separately from current network readings.

## Verification

- 169 adapter tests and 15 top-level tests passed after integration.
- Runtime readonly/locked/read-error SQLite cases, blocked guest reads, bounded background workers, retry and exact gap boundaries are regression-tested.
- A real local container under UID 65534, with networking disabled and read-only root filesystem, created a SQLite file in a fresh named volume. A replacement container read the retained value successfully.
- `qa_telemetry_history.py` uses an isolated native Dynacat renderer against actual read-only upstream data. Dark/light at 1600 and 390 pixels: 27 workload graphs, no static workload meters, no overflow or browser errors, disclosure state retained across refresh. No playback or downloads are initiated.
- Evidence: `/srv/hermes/workspaces/telemetry-history-qa/`.

Final production verification must read back the deployed revision, container health, persistent storage state, 1800-second graph windows, rendered graphs and exact metric-source coverage. Initial VM guest-OS history cannot contain measurements predating deployment.
