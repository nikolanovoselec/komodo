"""Read-only, allowlisted Proxmox telemetry, independent of Komodo availability."""
import time
import math
import json
import os
import ssl
import urllib.request
import urllib.parse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirected host or HTTP URL.
        return None


def _api(path):
    if path not in ('/nodes', '/cluster/resources?type=vm'):
        raise ValueError('Read endpoint not allowed')
    base = os.environ.get('PVE_URL', 'https://192.168.1.2:8006/api2/json').rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Verified HTTPS URL required')
    context = ssl.create_default_context(cafile=os.environ.get('PVE_CA_FILE', '/app/pve-root-ca.pem'))
    token_id = os.environ['DYNACAT_PROXMOX_TOKEN_ID']
    secret = os.environ['DYNACAT_PROXMOX_SECRET']
    request = urllib.request.Request(base + path, method='GET',
        headers={'Authorization': 'PVEAPIToken=' + token_id + '=' + secret, 'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), _NoRedirect())
    with opener.open(request, timeout=5) as response:
        return json.load(response)['data']


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


def collect(api=None):
    """Safe to embed as summary['pve']; errors do not fail Komodo collection."""
    try:
        return _collect(api if api is not None else _api)
    except Exception:
        return {'error': 'Proxmox telemetry unavailable; verify TLS, network and read API access',
                'fetched_at': int(time.time()), 'nodes': [], 'guests': None}


def _collect(api):
    """Return only node metrics and aggregate guest counts, never guest configuration."""
    nodes = api('/nodes')
    guests = api('/cluster/resources?type=vm')
    projected = []
    for node in nodes:
        cpu = _number(node.get('cpu'))
        projected.append({'name': node['node'], 'status': node.get('status', 'unknown'),
                          'cpu_percent': cpu * 100 if cpu is not None and cpu <= 1 else None,
                          'ram': _capacity(node.get('mem'), node.get('maxmem')),
                          'root_disk': _capacity(node.get('disk'), node.get('maxdisk')),
                          'guests': _counts([g for g in guests if g.get('node') == node['node']])})
    return {'error': None, 'fetched_at': int(time.time()), 'nodes': projected, 'guests': _counts(guests)}
