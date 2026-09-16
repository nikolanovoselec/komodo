# Networking lower-page release

## Delivered
- Expanded searchable connected clients at left, Pi-hole panel at right; mobile stacked.
- Removed VLAN, WiFi, firewall and source-capabilities lower panels.
- Existing infrastructure graph markup and styles preserved.
- Pi-hole unavailable states are explicit, with no synthetic live values.

## Blocked integration (verified from production collector)
Both pihole-master.lan (192.168.5.162) and pihole-slave.lan (192.168.5.92) run Pi-hole API v6. Collector 192.168.2.72 cannot connect to either on TCP 443. Discovery also found 22/80 unreachable. Required network authorization: collector to these two destinations TCP 443 only. No firewall change made.

Protected API authentication is not wired to collector. Existing Komodo PIHOLE_API_KEY is used elsewhere; do not copy or expose it. A follow-up needs protected variable wiring/resource synchronization and verified TLS trust, followed by authenticated runtime reads before backend implementation/deployment. No Pi-hole collector was deployed in this release. Template supports a future explicitly typed pihole object but is not evidence of integration.

Required endpoints: stats/summary, queries?length=10&upstream=permitted, queries?length=10&upstream=blocklist. Sessions belong exclusively server-side. Merge recent records by source timestamp; expose status to distinguish CACHE/FORWARDED and specific blocking classes. Gravity sums are not unique domains.

## Client transfer discovery
Live official UniFi Integration client list AND detail responses contain only type,id,name,connectedAt,ipAddress,macAddress,uplinkDeviceId,access. No traffic or signal metrics are exposed by these reads. Preserve unavailable rather than use device-uplink rates as per-client rates.

## Verification
Strict native-renderer RED/GREEN tests cover layout, missing source, unavailable != zero, latest-ten cap, statuses, refresh filtering/caret, mobile and CSS digest. Fixture Pi-hole available states are synthetic, not live integration. Captured-real source baseline/candidate screenshots and backups are local under networking-lower-qa. Deployed screenshots are separately named.
