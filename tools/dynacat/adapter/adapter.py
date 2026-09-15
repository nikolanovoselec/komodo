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


class PveSnapshot:
    """One process-wide, demand-driven PVE flight, independent of general I/O.

    Five seconds between completed attempts (including failures). Age is measured
    from collection start, not completion or the source's unknown sample time.
    The collector's existing 60s optional-read caches are left untouched.
    """
    def __init__(self, loader=None, clock=None):
        self.loader = loader or self._collect
        self.clock = clock or time.monotonic
        self.lock = threading.Condition()
        self.at = self.started = None
        self.data = None
        self.collecting = self.failed = False

    @staticmethod
    def _collect():
        import proxmox
        return proxmox.collect()

    def _refresh(self, started):
        try:
            data = self.loader()
            json.dumps(data)
            failed = bool(data.get('error'))
        except Exception:
            data, failed = None, True
        with self.lock:
            self.at, self.started = self.clock(), started
            self.data, self.failed, self.collecting = data, failed, False
            self.lock.notify_all()

    def snapshot(self, wait=False):
        with self.lock:
            now = self.clock()
            if not self.collecting and (self.at is None or now - self.at >= 5):
                self.collecting = True
                threading.Thread(target=self._refresh, args=(now,), daemon=True).start()
            if wait:
                while self.collecting:
                    self.lock.wait()
            age = None if self.started is None else self.clock() - self.started
            state = ('unavailable' if self.failed else 'starting' if self.data is None else
                     'expired' if age >= 30 else 'collecting' if self.collecting else 'cached')
            freshness = dict(state=state, collecting=self.collecting, age_seconds=age,
                             max_age_seconds=30, age_basis='collection_started',
                             fetched_at_basis='collection_completed_not_source_sample')
            if state in ('unavailable', 'starting', 'expired'):
                return {'error': 'Proxmox telemetry unavailable; verify TLS, network and read API access',
                        'fetched_at': (self.data or {}).get('fetched_at'),
                        'nodes': [], 'guests': None}, freshness, 503
            return self.data, freshness, 200


_pve_cache = PveSnapshot()


def make_server(address, loader, *, continuous=False, warmers=None, sample_interval=.25):
    """Share one demand-driven collection, never blocking /current on upstream I/O.

    Legacy /summary and /health wait for the current attempt via Condition.wait
    (which releases the reader lock). Successful and failed attempts both defer
    the next attempt for five seconds. The fast route serves the last snapshot
    only while younger than 30 seconds, measured conservatively from collection
    START, not completion; this bounds slow/hung refresh and late-result safety.
    Source-specific RRD/ZFS/GitHub caches remain independently governed upstream.
    """
    refresh_interval, max_age = 5, 30
    lock = threading.Condition()
    cached = {'at':None, 'data':None, 'failed':False, 'collecting':False,
              'sample_at':None}

    def refresh(started):
        # Never hold the reader lock across upstream I/O.
        try:
            data = loader()
            json.dumps(data)  # Serialization failure also invalidates the old sample.
            failed = False
        except Exception:
            data, failed = None, True
        with lock:
            cached.update(at=time.monotonic(), data=data, failed=failed,
                          collecting=False, sample_at=started)
            lock.notify_all()
    def kickoff():
        with lock:
            now = time.monotonic()
            if not cached['collecting'] and (cached['at'] is None or now - cached['at'] >= refresh_interval):
                cached['collecting'] = True
                threading.Thread(target=refresh, args=(now,), daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def do_GET(self):
            if self.path == '/network-current':
                import unifi
                data = unifi.current()
                status = 200 if data['state'] == 'available' else 503
                self.send_json(status, json.dumps(data).encode())
                return
            if self.path in ('/media-current', '/media-library', '/media-arr'):
                import media
                self.send_json(200, json.dumps(media.current(self.path.removeprefix('/media-'))).encode())
                return
            if self.path == '/pve-current':
                pve, freshness, status = _pve_cache.snapshot()
                data = dict(pve=pve, freshness=freshness)
                if status != 200:
                    data['error'] = pve['error']
                self.send_json(status, json.dumps(data).encode())
                return
            if self.path not in ('/summary', '/health', '/current'):
                self.send_error(404)
                return
            try:
                with lock:
                    kickoff()
                    if self.path != '/current':
                        while cached['collecting']:
                            lock.wait()
                    age = None if cached['sample_at'] is None else time.monotonic() - cached['sample_at']
                    state = ('unavailable' if cached['failed'] else
                             'starting' if cached['data'] is None else
                             'expired' if age is not None and age >= max_age else
                             'collecting' if cached['collecting'] else 'cached')
                    freshness = dict(state=state, collecting=cached['collecting'],
                                     age_seconds=age, max_age_seconds=max_age)
                    if state in ('unavailable', 'starting', 'expired'):
                        data = dict(error='Komodo telemetry unavailable; verify read API access',
                                    freshness=freshness)
                        status = 503
                    else:
                        data = cached['data']
                        if self.path == '/current':
                            data = dict(data, freshness=freshness)
                        status = 200
                payload = json.dumps(data).encode()
            except Exception:
                # Fail closed rather than showing an old healthy response or logging secrets.
                payload = b'{"error":"Komodo telemetry unavailable; verify read API access"}'
                status = 503
            self.send_json(status, payload)

        def send_json(self, status, payload):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    from telemetry import Sampler
    class Server(ThreadingHTTPServer):
        sampler: Sampler | None = None

        def shutdown(self):
            if self.sampler is not None:
                self.sampler.stop()
            super().shutdown()

        def server_close(self):
            if self.sampler is not None:
                self.sampler.stop()
            super().server_close()

    server = Server(address, Handler)
    if continuous:
        server.sampler = Sampler([kickoff, *(warmers or ())], interval=sample_interval)
        server.sampler.start()
    return server



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
        workloads.append(dict(id=s['id'], name=s['name'], server_id=i.get('server_id'), host=i.get('server_name') or 'Unassigned',
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
            disks.append(dict(name=s.get('name', s['id']), server_id=s['id'], url=komodo_url(s['id']),
                              used=used, total=total, percent=100*used/total))
    return dict(top_disk=sorted(disks, key=lambda d:d['percent'], reverse=True)[:5],
                fetched_at=int(time.time()), stacks_total=len(workloads), containers_total=len(kept),
                running_stacks=sum(s['state']=='running' for s in workloads),
                running_containers=sum(c['state']=='running' for c in kept),
                definition_issues=[s for s in workloads if s['unassigned']],
                stack_problems=[s for s in workloads if s['state']!='running' and not s['unassigned']],
                container_problems=problems, container_inventory=kept, groups=groups,
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
    result = project(servers, stacks, tags, containers, members)
    import vm_metrics
    pve, _, _ = _pve_cache.snapshot(wait=True)
    import workload_history
    result['pve'] = workload_history.enrich(vm_metrics.enrich(pve, servers))
    import navigation
    navigation.link_ranked_hosts(result, servers)
    import workload_docker
    workload_docker.enrich(result, servers)
    # Full inventory now lives once under each matched/unmatched Docker group.
    result.pop('container_inventory', None)
    import renovate
    result['renovate'] = renovate.collect()
    return result


def visible_stacks(servers, stacks, tags):
    disabled_tags = {t['_id']['$oid'] for t in tags if t['name'].lower() == 'disabled'}
    disabled_hosts = {s['id'] for s in servers if s['info']['state'] == 'Disabled'}
    return [s for s in stacks if not disabled_tags.intersection(s.get('tags', []))
            and s['info'].get('server_id') not in disabled_hosts]


def main():
    import media
    warmers = [_pve_cache.snapshot, *(source.snapshot for source in media.SOURCES.values())]
    if os.environ.get('DYNACAT_UNIFI_TOKEN'):
        import unifi
        warmers.append(unifi.current)
    with make_server(('0.0.0.0', 8090), lambda: collect(api),
                     continuous=True, warmers=warmers) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
