"""Join filtered Docker projections to audited guest identities, without I/O.

Only this module's guest ``docker`` field and summary ``docker_unmatched`` are
replaced. PVE telemetry is never substituted with Docker container accounting.
Unknown/missing host identities stay unmatched, never inferred from names.
"""
from copy import deepcopy
import math
import time
from urllib.parse import quote
from typing import Any

from vm_metrics import VERIFIED_BINDINGS
from navigation import LXC_BINDINGS


def _measured(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def _problem(row):
    return row.get('state') != 'running' or 'unhealthy' in str(row.get('status', '')).lower()


def _docker(server_id, server, containers, stacks, now):
    info = (server or {}).get('info') or {}
    refreshed = (info.get('stats') or {}).get('refresh_ts')
    age = (now - refreshed) / 1000 if _measured(refreshed) else None
    result: dict[str, Any] = dict(server_id=server_id, host=(server or {}).get('name') or
                  next((r.get('host') for r in containers + stacks if r.get('host')), server_id),
                  url='https://komodo.graymatter.ch/servers/' + quote(server_id, safe=''),
                  available=False, status='No Docker data', source='Komodo / Periphery',
                  source_refresh_ts=refreshed if _measured(refreshed) else None,
                  age_seconds=age, max_age_seconds=30,
                  running=None, total=None, failed=None, unhealthy=None,
                  cpu=None, ram_bytes=None, cpu_coverage=None, ram_coverage=None,
                  cpu_scope='Sum of measured running-container CPU; may exceed 100%',
                  ram_scope='Sum of measured running-container RAM; not host memory',
                  containers=[], stack_problems=deepcopy(sorted(stacks, key=lambda r: str(r.get('name', '')))))
    if info.get('state') != 'Ok':
        result['status'] = 'Docker host unavailable'
    elif age is None or not 0 <= age < 30:
        result['status'] = 'Stale Docker data'
    elif containers:
        rows = deepcopy(sorted(containers, key=lambda r: (not _problem(r), str(r.get('name', '')))))
        running = [c for c in rows if c.get('state') == 'running']
        cpu = [c['cpu'] for c in running if _measured(c.get('cpu'))]
        ram = [c['ram_bytes'] for c in running if _measured(c.get('ram_bytes'))]
        # Prevent invalid source measurements leaking NaN/Infinity to JSON or UI.
        for row in rows:
            for key in ('cpu', 'ram_bytes'):
                if not _measured(row.get(key)):
                    row[key] = None
        cpu_sum, ram_sum = sum(cpu) if cpu else None, sum(ram) if ram else None
        result.update(available=True, status='Available', containers=rows,
                      running=len(running), total=len(rows), failed=len(rows) - len(running),
                      unhealthy=sum('unhealthy' in str(c.get('status', '')).lower() for c in running),
                      cpu=cpu_sum if _measured(cpu_sum) else None,
                      ram_bytes=ram_sum if _measured(ram_sum) else None,
                      cpu_coverage=dict(measured=len(cpu), running=len(running)),
                      ram_coverage=dict(measured=len(ram), running=len(running)))
    return result


def enrich(summary, servers):
    """Mutate only Docker projection fields and return summary for composition.

    Input rows must already honor disabled stack membership policy. Servers with
    explicit Disabled state are additionally excluded here, including stacks.
    Source refresh_ts is milliseconds; future timestamps fail closed.
    """
    by_id = {s['id']: s for s in servers if isinstance(s, dict) and s.get('id')}
    disabled = {sid for sid, s in by_id.items() if (s.get('info') or {}).get('state') == 'Disabled'}
    containers, stacks = {}, {}
    for key, grouped in [('container_inventory', containers), ('stack_problems', stacks)]:
        for row in summary.get(key) or []:
            sid = row.get('server_id')
            if isinstance(sid, str) and sid and sid not in disabled:
                grouped.setdefault(sid, []).append(row)
    now = time.time() * 1000
    joined = set()
    for guest in (summary.get('pve') or {}).get('guest_inventory') or []:
        # Repeated enrichment must not retain previously healthy or disabled rows.
        guest.pop('docker', None)
        bindings = {'qemu': VERIFIED_BINDINGS, 'lxc': LXC_BINDINGS}.get(guest.get('type'), {})
        guest_id = guest.get('id')
        binding = bindings.get(guest_id) if type(guest_id) is int else None
        if not binding or guest.get('name') != binding[0]:
            continue
        sid = binding[1]
        server = by_id.get(sid)
        if sid in disabled or not server or (server.get('info') or {}).get('address') != binding[2]:
            continue
        joined.add(sid)
        guest['docker'] = _docker(sid, server, containers.get(sid, []), stacks.get(sid, []), now)
    summary['docker_unmatched'] = [
        dict(_docker(sid, by_id.get(sid), containers.get(sid, []), stacks.get(sid, []), now),
             reason='No verified current Proxmox guest identity')
        for sid in sorted((containers.keys() | stacks.keys()) - joined)]
    return summary
