"""Read-only, allowlisted Proxmox telemetry, independent of Komodo availability."""
import time
import math
import json
import os
import re
import ssl
import urllib.request
import urllib.parse
import threading
import copy


class SlowReadCache:
    """Single-flight 60s optional reads (including failures), not current status.

    pvestatd's upstream loop targets 10s (PVE/Service/pvestatd.pm,
    $updatetime = 10); 5s dashboard polling is not 5s source sampling.
    Hour RRD is 60s buckets; ZFS/storage reads need not follow every poll.
    """
    def __init__(self, read, clock=time.monotonic):
        self.read = read
        self.clock = clock
        self.lock = threading.Lock()
        self.entries = {}

    def __call__(self, path):
        if path in ('/nodes', '/cluster/resources?type=vm'):
            return self.read(path)
        with self.lock:
            now = self.clock()
            entry = self.entries.get(path)
            if entry is None or now - entry[0] >= 60:
                try:
                    data = self.read(path, allowed_rrd=frozenset([path]))
                    failed = False
                except Exception:
                    data, failed = None, True
                entry = (self.clock(), data, failed)
                # Bound cache size when nodes disappear or are renamed.
                self.entries = {k: v for k, v in self.entries.items()
                                if now - v[0] < 60}
                self.entries[path] = entry
            if entry[2]:
                raise RuntimeError('Optional Proxmox telemetry unavailable')
            return copy.deepcopy(entry[1])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirected host or HTTP URL.
        return None


def _api(path, allowed_rrd=frozenset()):
    # Membership alone cannot authorize arbitrary URLs. Optional paths must also
    # match this exact read-only grammar, with no extra queries or child endpoints.
    optional = path == '/storage' or re.fullmatch(
        r'/nodes/[A-Za-z0-9][A-Za-z0-9-]*/(?:disks/zfs|storage|(?:(?:qemu|lxc)/[1-9][0-9]*/)?rrddata\?timeframe=hour&cf=AVERAGE)', path)
    if path not in ('/nodes', '/cluster/resources?type=vm') and not (optional and path in allowed_rrd):
        raise ValueError('Read endpoint not allowed')
    base = os.environ.get('PVE_URL', 'https://192.168.1.2:8006/api2/json').rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Verified HTTPS URL required')
    context = ssl.create_default_context(cafile=os.environ.get('PVE_CA_FILE', '/app/pve-root-ca.pem'))
    # Legacy PVE cluster CAs lack the keyUsage extension required by Python 3.13's
    # STRICT default. Relax only that context's RFC strictness, not trust or
    # hostname verification: CERT_REQUIRED and check_hostname remain enabled.
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    token_id = os.environ['DYNACAT_PROXMOX_TOKEN_ID']
    secret = os.environ['DYNACAT_PROXMOX_SECRET']
    request = urllib.request.Request(base + path, method='GET',
        headers={'Authorization': 'PVEAPIToken=' + token_id + '=' + secret, 'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), _NoRedirect())
    with opener.open(request, timeout=2) as response:
        return json.load(response)['data']


def resource_url(kind, identity):
    """Installed PVE History.js v1 state: rid + resource-specific Summary tab."""
    if kind == 'node':
        valid = isinstance(identity, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', identity)
        suffix = '4:5::::::'
    elif kind in ('qemu', 'lxc'):
        valid = isinstance(identity, int) and not isinstance(identity, bool) and identity > 0
        suffix = '4:::::5::' if kind == 'qemu' else '4::::::5:'
    else:
        return None
    if not valid:
        return None
    rid = urllib.parse.quote(f'{kind}/{identity}', safe='')
    return f'https://proxmox.graymatter.ch/#v1:0:={rid}:{suffix}'


def _counts(guests):
    return {kind: {'running': sum(g.get('status') == 'running' for g in guests if g.get('type') == kind),
                   'total': sum(g.get('type') == kind for g in guests)} for kind in ('qemu', 'lxc')}


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return value
    return None


def _capacity(used, total):
    used, total = _number(used), _number(total)
    percent = 100 * used / total if used is not None and total and used <= total else None
    return {'used_bytes': used, 'total_bytes': total, 'percent': percent}


_cached_api = SlowReadCache(_api)


def collect(api=None):
    """Safe to embed as summary['pve']; errors do not fail Komodo collection."""
    try:
        return _collect(api if api is not None else _cached_api)
    except Exception:
        return {'error': 'Proxmox telemetry unavailable; verify TLS, network and read API access',
                'fetched_at': int(time.time()), 'nodes': [], 'guests': None}


def _node_order(node):
    name = node['node'].lower()
    match = re.fullmatch(r'(.*?)([ivxlcdm]+)', name)
    if match:
        values = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
        digits = [values[c] for c in match[2]]
        number = sum(-v if i + 1 < len(digits) and v < digits[i + 1] else v
                     for i, v in enumerate(digits))
        return (match[1], number, name)
    return (name, 0, name)


def _history(rows, now=None):
    end = time.time() if now is None else now
    duration = 1800
    start = end - duration
    rows = sorted({r['time']: r for r in rows if isinstance(r, dict)
                   and _number(r.get('time')) is not None
                   and start <= r['time'] <= end}.values(), key=lambda r: r['time'])
    valid = [r for r in rows if _number(r.get('cpu')) is not None and r['cpu'] <= 1]
    # Proxmox pvestatd sums physical NIC byte counters; pmxcfs/status.c
    # stores netin/netout as DERIVE. RRD values are already bytes/second.
    rates = [_number(r.get(key)) for r in rows for key in ('netin', 'netout')]
    rates = [value for value in rates if value is not None]
    scale = (max(rates) or 1) if rates else None

    def segments(key):
        metric_scale = 1 if key == 'cpu' else scale
        result, segment = [], []
        previous = None
        for row in rows:
            value = _number(row.get(key))
            if key == 'cpu' and value is not None and value > 1:
                value = None
            # The hour RRD uses one-minute buckets. Missing buckets and invalid
            # values are gaps, not zero traffic or permission to interpolate.
            if value is None or (previous is not None and row['time'] - previous != 60):
                if len(segment) >= 2:
                    result.append(' '.join(segment))
                segment = []
            if value is not None and metric_scale is not None:
                x = 100 * (row['time'] - start) / duration
                segment.append(f'{x:g},{30 * (1 - value / metric_scale):g}')
            previous = row['time']
        if len(segment) >= 2:
            result.append(' '.join(segment))
        return result

    latest = rows[-1] if rows and end - rows[-1]['time'] <= 120 else {}
    return {'history': {'cpu_segments': segments('cpu'), 'samples': len(valid), 'window': '30m',
                        'start_time': start, 'end_time': end, 'duration_seconds': duration,
                        'net_rx_segments': segments('netin'), 'net_tx_segments': segments('netout'),
                        'net_scale_bytes_sec': scale},
            'net_in_bytes_sec': _number(latest.get('netin')),
            'net_out_bytes_sec': _number(latest.get('netout'))}


def _zfs_capacity(name, used, total, free, scope):
    result = {'name': name, **_capacity(used, total), 'free_bytes': _number(free), 'scope': scope}
    if (result['percent'] is None or result['free_bytes'] is None
            or result['free_bytes'] > (result['total_bytes'] or 0)
            or (scope == 'physical_pool' and result['used_bytes'] is not None
                and result['free_bytes'] is not None and result['total_bytes'] is not None
                and result['used_bytes'] + result['free_bytes'] != result['total_bytes'])):
        result.update(used_bytes=None, total_bytes=None, free_bytes=None, percent=None)
    return result


def _zfs(node, api):
    unavailable = {'zfs': None, 'zfs_state': 'unavailable',
                   'zfs_error': 'ZFS telemetry unavailable; verify read API access'}
    if node.get('status') != 'online':
        return {**unavailable, 'zfs_state': 'offline', 'zfs_error': 'Node offline'}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', node['node']):
        return unavailable
    path = '/nodes/' + node['node'] + '/disks/zfs'
    try:
        rows = _api(path, allowed_rrd=frozenset([path])) if api is _api else api(path)
        if not isinstance(rows, list) or any(not isinstance(r, dict)
                or not isinstance(r.get('name'), str) or not r['name'] for r in rows):
            return unavailable
        pools = {r['name']: _zfs_capacity(r['name'], r.get('alloc'), r.get('size'),
                                         r.get('free'), 'physical_pool')
                 for r in rows if isinstance(r, dict) and isinstance(r.get('name'), str)}
        values = [pools[k] for k in sorted(pools)]
        invalid = any(p['percent'] is None for p in values)
        return {'zfs': values, 'zfs_state': 'unavailable' if invalid else 'ok' if values else 'none',
                'zfs_error': 'Invalid ZFS pool capacity' if invalid else None}
    except Exception:
        pass
    # Storage accounting is not zpool allocation. Never add alias or child-dataset
    # capacities: select the shallowest active dataset as one representative per
    # pool. Keep dataset name and fallback scope so it cannot masquerade as pool use.
    try:
        storage_path = '/nodes/' + node['node'] + '/storage'
        allowed = frozenset(['/storage', storage_path])
        read = (lambda p: _api(p, allowed_rrd=allowed)) if api is _api else api
        configs, statuses = read('/storage'), read(storage_path)
        by_id = {s['storage']: s for s in statuses if isinstance(s, dict) and 'storage' in s}
        candidates = []
        for config in configs:
            if not isinstance(config, dict) or config.get('type') != 'zfspool':
                continue
            pool = config.get('pool')
            if not isinstance(pool, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)*', pool):
                continue
            status = by_id.get(config.get('storage'), {})
            if status.get('type') != 'zfspool' or status.get('active') != 1 or status.get('enabled') != 1:
                continue
            candidates.append((pool.count('/'), pool, config['storage'], status))
        selected = {}
        for _, pool, _, status in sorted(candidates, key=lambda c: c[:3]):
            root = pool.split('/')[0]
            if root not in selected:
                selected[root] = _zfs_capacity(pool, status.get('used'), status.get('total'),
                                                status.get('avail'), 'zfs_backed_storage')
        values = [selected[k] for k in sorted(selected)]
        if not values:
            return {**unavailable, 'zfs_error': 'Physical ZFS pools unavailable; no active identified ZFS-backed storage'}
        invalid = any(p['percent'] is None for p in values)
        return {'zfs': values, 'zfs_state': 'unavailable' if invalid else 'fallback',
                'zfs_error': 'Invalid ZFS-backed storage capacity' if invalid else
                    'ZFS-backed storage accounting, not physical pool capacity; one representative dataset per pool'}
    except Exception:
        return unavailable


def _guest_inventory(guests):
    result = []
    for guest in guests:
        if guest.get('type') not in ('qemu', 'lxc'):
            continue
        running = guest.get('status') == 'running'
        cpu = _number(guest.get('cpu')) if running else None
        # VM disk is allocated virtual capacity, not guest filesystem usage.
        disk_valid = running and guest['type'] == 'lxc' and (_number(guest.get('disk')) or 0) > 0
        ram = _capacity(guest.get('mem') if running else None, guest.get('maxmem'))
        # QEMU host accounting includes emulator overhead and can legitimately
        # exceed configured guest RAM. Preserve measured bytes and disclose the
        # denominator instead of rejecting these readings as impossible capacity.
        if guest['type'] == 'qemu' and ram['used_bytes'] is not None and ram['total_bytes']:
            ram['percent'] = 100 * ram['used_bytes'] / ram['total_bytes']
        result.append({'id': guest.get('vmid'), 'name': guest.get('name') or str(guest.get('vmid')),
                       'node': guest.get('node', 'unknown'), 'type': guest['type'],
                       'url': resource_url(guest['type'], guest.get('vmid')),
                       'status': guest.get('status', 'unknown'),
                       'cpu_percent': cpu * 100 if cpu is not None and cpu <= 1 else None,
                       'ram': ram,
                       'disk': _capacity(guest.get('disk') if disk_valid else None, guest.get('maxdisk')),
                       'memory_scope': 'Host-accounted VM memory' if guest['type'] == 'qemu' else 'Container memory'})
    return sorted(result, key=lambda g: (g['id'] or 0, g['name']))


def _collect(api):
    """Return allowlisted node/guest metrics, never guest configuration."""
    nodes = api('/nodes')
    # Explicit per-collection allowlist, derived only from safe discovered node names.
    rrd_paths = {n['node']: '/nodes/' + n['node'] + '/rrddata?timeframe=hour&cf=AVERAGE'
                 for n in nodes if isinstance(n.get('node'), str)
                 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', n['node'])}
    allowed_rrd = frozenset(rrd_paths.values())
    guests = api('/cluster/resources?type=vm')
    projected = []
    for node in sorted(nodes, key=_node_order):
        history = _history([])
        if node.get('status') == 'online' and node['node'] in rrd_paths:
            try:
                path = rrd_paths[node['node']]
                rows = _api(path, allowed_rrd=allowed_rrd) if api is _api else api(path)
                history = _history(rows)
            except Exception:
                pass  # Optional history must never erase current node telemetry.

        cpu = _number(node.get('cpu'))
        projected.append({'name': node['node'], 'url': resource_url('node', node['node']),
                          'status': node.get('status', 'unknown'), **history,
                          **_zfs(node, api),
                          'cpu_percent': cpu * 100 if cpu is not None and cpu <= 1 else None,
                          'ram': _capacity(node.get('mem'), node.get('maxmem')),
                          'root_disk': _capacity(node.get('disk'), node.get('maxdisk')),
                          'guests': _counts([g for g in guests if g.get('node') == node['node']])})
    return {'error': None, 'fetched_at': int(time.time()), 'nodes': projected,
            'guests': _counts(guests), 'guest_inventory': _guest_inventory(guests)}
