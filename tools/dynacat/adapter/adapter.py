"""Read-only Komodo workload projection; never exposes configuration or credentials."""
import re
import time
import json
import os
import threading
import urllib.request
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def api(kind, params):
    # Fixed read endpoint and allowlist: no proxying caller input or write API.
    if kind not in {'ListServers', 'ListStacks', 'ListTags', 'ListAllDockerContainers', 'GetStack'}:
        raise ValueError('Read type not allowed')
    request = urllib.request.Request(os.environ.get('KOMODO_URL', 'http://192.168.5.53:9120/read'),
        data=json.dumps({'type':kind, 'params':params}).encode(),
        headers={'Content-Type':'application/json', 'X-Api-Key':os.environ['DYNACAT_KOMODO_API_KEY'],
                 'X-Api-Secret':os.environ['DYNACAT_KOMODO_API_SECRET']}, method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def make_server(address, loader):
    lock = threading.Lock()
    cached = {'at':0, 'data':None}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def do_GET(self):
            if self.path not in ('/summary', '/health'):
                self.send_error(404)
                return
            try:
                with lock:
                    if time.monotonic() - cached['at'] > 15:
                        cached['data'] = loader()
                        cached['at'] = time.monotonic()
                    payload = json.dumps(cached['data']).encode()
                status = 200
            except Exception:
                # Fail closed rather than showing an old healthy response or logging secrets.
                payload = b'{"error":"Komodo telemetry unavailable; verify read API access"}'
                status = 503
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return ThreadingHTTPServer(address, Handler)



def number(value):
    try:
        return float(str(value).rstrip('%'))
    except (ValueError, TypeError):
        return None


def memory_bytes(value):
    match = re.fullmatch(r'([\d.]+)\s*(B|[KMGT]i?B)', str(value).split('/')[0].strip(), re.I)
    if not match:
        return None
    unit = match[2].upper()
    exponent = 'BKMGT'.index(unit[0])
    return float(match[1]) * (1024 if 'I' in unit else 1000) ** exponent


def komodo_url(server_id, container_name=None):
    # Komodo ui/src/router.tsx and components/docker/link.tsx.
    url = 'https://komodo.graymatter.ch/servers/' + quote(server_id, safe='')
    if container_name is not None:
        url += '/container/' + quote(container_name, safe='')
    return url


def project(servers, stacks, tags, containers, disabled_members):
    visible = visible_stacks(servers, stacks, tags)
    disabled_hosts = {s['id'] for s in servers if s['info']['state'] == 'Disabled'}
    workloads = []
    for s in visible:
        i = s['info']
        workloads.append(dict(id=s['id'], name=s['name'], host=i.get('server_name') or 'Unassigned',
                              state=i.get('state', 'unknown'), status=i.get('status') or i.get('state', 'unknown'),
                              unassigned=not i.get('server_id') and not i.get('swarm_id')))
    kept = []
    for c in containers:
        if c['server_id'] in disabled_hosts or (c['server_id'], c['name']) in disabled_members:
            continue
        stats = c.get('stats') or {}
        kept.append(dict(name=c['name'], host=c['server_name'], server_id=c['server_id'],
                         url=komodo_url(c['server_id'], c['name']), state=c.get('state', 'unknown'),
                         status=c.get('status', ''), cpu=number(stats.get('cpu_perc')),
                         ram_bytes=memory_bytes(stats.get('mem_usage')), ram=stats['mem_usage'].split('/')[0].strip() if stats.get('mem_usage') else 'N/A'))
    problems = [c for c in kept if c['state'] != 'running' or 'unhealthy' in c['status'].lower()]
    groups = []
    for host in sorted({s['host'] for s in workloads}):
        active = [s for s in workloads if s['host'] == host and s['state'] == 'running']
        if active:
            groups.append(dict(host=host, count=len(active), stacks=sorted(active, key=lambda s:s['name'])))
    disks = []
    for s in servers:
        stats = s['info'].get('stats') or {}
        used, total = number(stats.get('disk_used_gb')), number(stats.get('disk_total_gb'))
        if s['info']['state'] == 'Ok' and used is not None and total is not None and 0 <= used <= total and 0 < total < float('inf'):
            disks.append(dict(name=s.get('name', s['id']), url=komodo_url(s['id']),
                              used=used, total=total, percent=100*used/total))
    return dict(top_disk=sorted(disks, key=lambda d:d['percent'], reverse=True)[:5],
                fetched_at=int(time.time()), stacks_total=len(workloads), containers_total=len(kept),
                running_stacks=sum(s['state']=='running' for s in workloads),
                running_containers=sum(c['state']=='running' for c in kept),
                definition_issues=[s for s in workloads if s['unassigned']],
                stack_problems=[s for s in workloads if s['state']!='running' and not s['unassigned']],
                container_problems=problems, groups=groups,
                top_cpu=sorted([c for c in kept if c['state']=='running' and c['cpu'] is not None], key=lambda c:c['cpu'], reverse=True)[:5],
                top_ram=sorted([c for c in kept if c['state']=='running' and c['ram_bytes'] is not None], key=lambda c:c['ram_bytes'], reverse=True)[:5])

def collect(api):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        kinds = ['ListServers', 'ListStacks', 'ListTags', 'ListAllDockerContainers']
        futures = [pool.submit(api, k, {} if k == 'ListTags' else {'limit': 0}) for k in kinds]
        servers, stacks, tags, containers = [f.result() for f in futures]
        visible_ids = {s['id'] for s in visible_stacks(servers, stacks, tags)}
        # Resolve only hidden stacks on enabled hosts, using exact deployed service names.
        disabled_hosts = {s['id'] for s in servers if s['info']['state'] == 'Disabled'}
        hidden = [s for s in stacks if s['id'] not in visible_ids and s['info'].get('server_id') not in disabled_hosts]
        details = list(pool.map(lambda s: api('GetStack', {'stack': s['id']}), hidden))
    members = {(s['info'].get('server_id'), item['container_name'])
               for s, detail in zip(hidden, details)
               for item in detail['info'].get('deployed_services', []) if item.get('container_name')}
    import proxmox
    result = project(servers, stacks, tags, containers, members)
    result['pve'] = proxmox.collect()
    import renovate
    result['renovate'] = renovate.collect()
    return result


def visible_stacks(servers, stacks, tags):
    disabled_tags = {t['_id']['$oid'] for t in tags if t['name'].lower() == 'disabled'}
    disabled_hosts = {s['id'] for s in servers if s['info']['state'] == 'Disabled'}
    return [s for s in stacks if not disabled_tags.intersection(s.get('tags', []))
            and s['info'].get('server_id') not in disabled_hosts]


if __name__ == '__main__':
    make_server(('0.0.0.0', 8090), lambda: collect(api)).serve_forever()
