# UniFi Network Integration — verified read-only backend

## Frontend contract: `GET /network-current`

Independent of `/current` and `/pve-current`. HTTP 200 for a usable inventory (including explicitly partial sections); HTTP 503 for `starting`, `stale`, or `error`. Always `Cache-Control: no-store`.

Top-level:
- `state`: `available | starting | stale | error`; `error`: null or generic safe error.
- `site:{id,name}`, `application_version`, `collected_at` (collection start, **not** metric sample time).
- `summary:{devices_total,devices_online,clients_total,clients_wired,clients_wireless,networks_total,wifi_total}`. Incomplete collection counts are **null**, not misleading partial totals or zero.
- `devices`, `clients`, `networks`, `wifi`, `wan`, `wan_connections`, `firewall`, `capabilities`, `partial`.
- `endpoints`: map of section to `{state,partial,total,returned}`. Unsupported/not-configured capability is distinct from a failed or truncated read.
- `freshness:{age_seconds,max_age_seconds:30,age_basis:'collection_started',collecting}` on HTTP snapshots.

### Device / topology fields
`devices[]:{id,name,model,kind,state,ip,uptime_seconds,cpu_percent,memory_percent,rx_mbps,tx_mbps,ports_active,ports_total,clients_count,url,source_timestamp,metrics_state,history,ports,radios,uplink_device_id}`.

- `kind`: `gateway | access-point | switch | other`. Gateway model identification is explicit because this UDM advertises only the `switching` feature.
- `state` is the provider inventory state (`ONLINE`, etc). `metrics_state` is `available | stale | unavailable` independently.
- Uplink `rx_mbps`/`tx_mbps` use decimal Mbps from API `rxRateBps`/`txRateBps`. They represent the **device uplink**, not independently verified WAN/interface throughput. Do not label AP/switch uplink traffic as Internet traffic or sum device rates into LAN throughput (double counting).
- `source_timestamp` is parsed timezone-aware `lastHeartbeatAt`. Missing, invalid, future or older-than-120-second samples do not supply current metric values. Poll time is never substituted.
- `url` is null: no verified provider device deep link was established. Do not invent one.
- `ports[]:{index,state,connector,speed_mbps,max_speed_mbps,poe_enabled,poe_state}`. Link speed is capacity/negotiation, **not traffic**.
- `radios[]:{frequency_ghz,channel,channel_width_mhz,standard}`.
- `uplink_device_id` joins actual device IDs for topology; no inferred physical-port mapping.

### Other collections
- `clients[]:{id,name,kind,ip,network,device,signal_dbm,rx_mbps,tx_mbps}`. Kind `wired | wireless | other`; `device` is the actual uplink device ID. Network/signal/rates are null when not exposed. No client MACs.
- `networks[]:{id,name,vlan,subnet,purpose,enabled}`. Subnet is canonical CIDR from detail `ipv4Configuration.hostIpAddress/prefixLength`; purpose currently carries the provider `management` classification, not a guessed policy role.
- `wifi[]:{id,name,security,bands,enabled}`. Security is **type only**; passwords/PSKs and other configuration details never pass through. Bands may be null.
- `wan:{available,state,rx_mbps,tx_mbps,reason}` remains unavailable because the official list has no verified operational health or measured per-WAN traffic. `wan_connections[]:{id,name}` lists actual configured WANs.
- `firewall:{available,reason,rules,acl_count}`. Rule projection is restricted to `{id,name,enabled,action}` pending actual readable rules. The deployed gateway rejects official zone-policy and zone-list reads because zone-based firewall is not configured. Empty `rules` therefore **does not mean no firewall rules**. Legacy firewall rules are not exposed through the verified Integration endpoints; never enable/migrate/change the firewall to populate this widget.
- `capabilities[]:{name,available,reason}` explains supported reads and unavailable metrics.

Unknown numeric data is null, never fabricated zero. In `starting/stale/error`, current inventories are empty and summary numbers null; the UI must respect `state`. MACs, secrets, raw upstream error bodies, and access tokens are excluded.

## History

`history:{cpu,ram,rx,tx}`; each chart is `{path,area_path,dots,samples,scale,start,end,window_seconds:1800,state,source,persistence_state,unit}`. `area_path` is available with the current shared renderer. SVG viewBox is `0 0 100 30`; dots have `{x,y}`. CPU/RAM use percent. RX/TX share the same scale **per device**, in Mbps, chosen from observed values (minimum display scale 0.001 Mbps). Do not compare different devices' graph heights without their scale labels.

Only actual source-heartbeat samples are persisted, deduplicated by site/device/metric/timestamp, trimmed to `[now-1800,now]`. No backfill, resampling, or invented pre-start history. Gaps of 90 seconds or invalid values split paths. Repeated stale reads do not overwrite historical values. SQLite uses the existing `workload_history.Store`; in-memory fallback is explicitly reported if persistence is unavailable. Zero/one point remains collecting rather than fabricated history.

## Verified gateway/API evidence

Authenticated GET probes and final source staging ran in the existing tools collector interpreter through authenticated SSH. The token remained in its remote environment throughout; only allowlisted projection data returned. No gateway writes, container changes, commits, or deployment performed by this backend task.

Gateway Network version: **10.4.57**. Site **88f7af54-98f8-306a-a1c7-c9349722b1f6**, Default.
Base: `https://192.168.1.1/proxy/network/integration/v1/`.

| Endpoint (GET only) | Live status | Verified capability |
|---|---|---|
| `info` | 200 | applicationVersion 10.4.57 |
| `sites` | 200 | Default site |
| `sites/{id}/devices` | 200 | 7 adopted devices: 3 U6+, 2 USW Lite, U-LTE-Pro, UDM SE; all online in staged sample |
| `sites/{id}/devices/{id}` | 200 | ports/link speeds/PoE, AP radio channel/width/standard, real uplink device IDs |
| `sites/{id}/devices/{id}/statistics/latest` | 200 | uptime, CPU, RAM, uplink rates, lastHeartbeatAt for all 7 devices |
| `sites/{id}/clients` | 200 | bounded pagination verified; latest stage 42 clients, 16 wired/26 wireless (not constants) |
| `sites/{id}/clients/{id}` | 200 probe | same basic wireless detail, no signal or client rates; not polled repeatedly |
| `sites/{id}/networks` | 200 | 11 names/VLANs/enabled flags |
| `sites/{id}/networks/{id}` | 200 | all 11 staged subnets from IPv4 detail; DHCP configuration deliberately excluded |
| `sites/{id}/wifi/broadcasts` | 200 | 4 broadcasts, security types, optional bands |
| `sites/{id}/wans` | 200 | 3 configured WAN names, no health/traffic |
| `sites/{id}/wans/{id}` | 404 probe | no detail at this endpoint; not polled repeatedly |
| `sites/{id}/firewall/policies` | 400 | `api.firewall.zone-based-firewall-not-configured` |
| `sites/{id}/firewall/zones` | 400 | same not-configured capability |
| `sites/{id}/firewall/rules` | 404 probe | no legacy-rule resource at this path |
| `sites/{id}/acl-rules` | 200 | verified zero ACL rules; not a statement about legacy firewall rules |

An initial two-collection run separated by 35 seconds produced two distinct source samples on all seven devices. The final-source repeat verified shared RX/TX scales, available metrics, all 11 subnets and `partial:false`; six devices advanced to two samples while one AP retained its unchanged heartbeat as **one** deduplicated sample. Latest sanitized projection: `/tmp/unifi-live-projection.json` (local staging artifact, not committed, not a replay source). It contains private LAN labels/addresses; do not publish it externally.

Official references: https://developer.ui.com/network/v10.0.162/gettingstarted and https://developer.ui.com/network/v9.5.21/getdevicelateststatistics . Public reference fields were inspected; actual gateway version is newer, so live capability/status evidence above is retained. No private/legacy API fallback.

## Transport and operational bounds

- Fixed gateway/site and allowlisted GET paths only. No caller-provided host, URL, token, action or method; redirects rejected.
- Exact SHA-256 certificate pin is checked **on the same TLS connection before sending X-API-KEY**. The self-signed certificate uses `unifi.local`, not the gateway IP; this narrowly scoped pin replaces CA/hostname validation only for this transport. No process-wide TLS weakening.
- Public pin obtained over the trusted LAN via authenticated SSH: `9c:24:23:e4:df:3e:ba:16:5f:10:8d:a3:77:1e:d4:f9:19:e7:3f:c9:97:4f:36:60:6d:b6:b5:68:23:cc:33:10`. Rotation fails closed; independently reverify before updating optional `DYNACAT_UNIFI_CERT_SHA256`. TOFU is not an independently authenticated initial gateway identity.
- Socket timeout at most 4s, shared collection request budget 20s, wall timer shuts down a response socket against trickle/hanging bodies. Body maximum 2MB. No retry storms or credential-bearing exception logs.
- List pages default 100 records × 5 pages (500 records); hard API helper caps 100 × 10. Strict count/offset/total/duplicate validation, explicit partial markers on truncation, mutation, empty premature pages and errors.
- At most 32 devices get detail/stats and at most 50 networks get details per collection; overflow is explicitly partial. No unbounded worker pool.
- Live device list, client list and statistics are never metadata-cached. Other metadata uses a bounded 256-entry 60-second cache. Port/radio/configuration fields can therefore be up to 60 seconds old; cache errors never silently extend old entries. Snapshot publication has a separate five-second cooldown and 30-second expiry measured from the **published collection's start**, not a subsequent refresh start.

## Runtime/Compose handoff

1. Keep `DYNACAT_UNIFI_TOKEN` injected **only into workload-summary** from protected Komodo variables (already present); never pass it into Dynacat/browser config.
2. Add `UNIFI_HISTORY_PATH: /history/unifi.sqlite` to workload-summary. Existing `/history` volume must stay writable by UID/GID 65534. Without this variable, explicit in-memory mode works but restart retention does not.
3. Existing `./adapter:/app:ro` mount includes `unifi.py`; standard library only, no new runtime packages/certificate-file mounts.
4. Central lifecycle collector must invoke `unifi.current()` continuously, even without browsers. It is a nonblocking pump: one refresh worker and fast snapshot, five-second minimum cooldown after completion. Alternatively use `_SOURCE.refresh()` plus `_SOURCE.snapshot()` directly. No independent recurring scheduler is implemented here, to avoid conflicting with the parent-owned lifecycle scheduler.
5. Normal minimum-cadence load is 9 GETs per warm collection (7 stats + devices + clients), with roughly 35 reads for cold metadata on this estate. Source heartbeats are often tens of seconds apart; one-second frontend polling is not one-second source sampling. Increasing cadence does not produce more source points.
6. Route new widgets to `http://workload-summary:8090/network-current`. Render state/partial/capability explanations, not invented WAN/client metrics. No link should contain credentials.

## Tests

`/srv/hermes/workspaces/dynacat-qa-venv/bin/python -m pytest adapter/test_unifi.py -q`

Strict red/green slices cover projection secrecy, bounded/invalid pagination, metadata isolation, no-token-before-pin/path allowlist, total response deadline, partial failure, unsupported firewall, topology/subnets, source-time rejection, shared RX/TX scale, stale historical retention, persistent deduplication, nonblocking single-flight and scheduler hooks, snapshot expiry during an in-flight refresh, safe errors, and independent HTTP route/no-store headers. Full adapter suite also exercised; see final task report for latest totals.
