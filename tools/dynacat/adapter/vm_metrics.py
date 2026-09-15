"""Guest metrics from independently verified VM -> Periphery identities only.

Identity audit 2026-09-15 (read-only SSH, no API allowlist changes): PVE
/etc/pve/nodes/*/qemu-server/*.conf net0 MAC matched the interface carrying
Komodo GetServer config.address in `ip -j address show` on each guest.
All ipconfig0 values were DHCP, so names/IP assumptions were NOT sufficient.
VM 126 additionally verified Core container network mode=host and host :8120
listener on 192.168.5.53, proving its localhost Periphery endpoint.
VM 100/openclaw verified locally: this Hermes host has eth0 MAC
bc:24:11:2c:af:40 and IP 192.168.3.203, matching PVE net0 and Komodo address.

Static bindings require a fresh audit after VM recreation/IP reassignment.
No network access here; runtime uses existing ListServers address and stats.
"""
from copy import deepcopy
import math
import time

# VMID: (last audited display name, immutable Komodo server ID, verified endpoint, MAC)
# Display names are mutable labels, not identity. Runtime joins require the exact
# audited VMID + immutable server ID + endpoint, with healthy/fresh telemetry.
# MAC/IP evidence is audited out-of-band; this is not automatic VM discovery.
VERIFIED_BINDINGS = {
    100: ('hermes', '6a9adf2e489ba7b3562cb584', 'https://192.168.3.203:8120', 'bc:24:11:2c:af:40'),
    102: ('servarr', '680f79d06a6313ac1f9f2aba', 'https://192.168.2.38:8120', '02:e7:d8:db:ce:6c'),
    110: ('middleware', '680f79cf6a6313ac1f9f2ab7', 'https://192.168.5.148:8120', 'bc:24:11:a2:3b:7a'),
    111: ('pihole-master', '68153670e9fea328ad8cc7a0', 'https://192.168.5.162:8120', 'bc:24:11:69:01:02'),
    126: ('komodo-core', '680f79376a6313ac1f9f2a9b', 'https://localhost:8120', 'bc:24:11:ed:57:62'),
    131: ('tools', '6819f646d0f8c95b939cbf2f', 'https://192.168.2.72:8120', 'bc:24:11:d3:de:d5'),
}


def _capacity(used, total):
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in (used, total)) or not 0 <= used <= total or total <= 0):
        return None
    # Periphery's *_gb values are GiB (bytes / 1024**3), not decimal GB.
    return {'used_bytes': used * 1024**3, 'total_bytes': total * 1024**3,
            'percent': 100 * used / total}


def enrich(pve_result, servers):
    """Return a copy; keep PVE inventory, LXC, host RAM and unavailable data intact."""
    result = deepcopy(pve_result)
    by_id = {s.get('id'): s for s in servers if isinstance(s, dict)}
    now = time.time() * 1000
    for guest in result.get('guest_inventory') or []:
        if guest.get('type') != 'qemu' or guest.get('status') != 'running':
            continue
        guest_id = guest.get('id')
        binding = VERIFIED_BINDINGS.get(guest_id) if type(guest_id) is int else None
        if not binding:
            continue
        info = (by_id.get(binding[1]) or {}).get('info') or {}
        if info.get('state') != 'Ok' or info.get('address') != binding[2]:
            continue
        stats = info.get('stats') or {}
        refreshed = stats.get('refresh_ts')
        if (isinstance(refreshed, bool) or not isinstance(refreshed, (int, float))
                or not math.isfinite(refreshed) or not -30000 <= now - refreshed <= 120000):
            continue
        ram = _capacity(stats.get('mem_used_gb'), stats.get('mem_total_gb'))
        disk = _capacity(stats.get('disk_used_gb'), stats.get('disk_total_gb'))
        has_guest_ram = ('guest' in str(guest.get('memory_scope', '')).lower()
                         and guest.get('memory_source') != 'Komodo'
                         and (guest.get('ram') or {}).get('percent') is not None)
        if ram is not None and not has_guest_ram:
            guest.setdefault('pve_host_ram', deepcopy(guest.get('ram')))
            guest.update(ram=ram, memory_source='Komodo', memory_scope='Guest OS memory (Komodo / Periphery)')
        has_guest_disk = ((guest.get('disk') or {}).get('percent') is not None
                          and guest.get('disk_source') != 'Komodo')
        if disk is not None and not has_guest_disk:
            guest.update(disk=disk, disk_source='Komodo', disk_scope='Guest filesystem usage (Komodo / Periphery)')
    return result
