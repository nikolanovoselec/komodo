"""Source-separated real guest histories. No resampling or fabricated backfill."""
import math
import sqlite3
import threading
import time
import re
import os


class Store:
    def __init__(self, path=':memory:'):
        self.lock = threading.RLock()
        self.memory = {}
        self.state = 'memory' if path == ':memory:' else 'ready'
        try:
            self.db = sqlite3.connect(path, timeout=0.05, check_same_thread=False)
            self.db.execute('CREATE TABLE IF NOT EXISTS samples (identity TEXT, metric TEXT, ts REAL, value REAL, PRIMARY KEY(identity,metric,ts))')
        except sqlite3.Error:
            self.state = 'unavailable'
            self.db = sqlite3.connect(':memory:', check_same_thread=False)
            self.db.execute('CREATE TABLE samples (identity TEXT, metric TEXT, ts REAL, value REAL, PRIMARY KEY(identity,metric,ts))')

    def __del__(self):
        if hasattr(self, "db"):
            self.db.close()

    def add(self, identity, metric, ts, value, now):
        if number(ts) is None or not now-WINDOW <= ts <= now:
            return
        with self.lock:
            self.memory = {k: v for k, v in self.memory.items() if now-WINDOW <= k[2] <= now}
            self.memory[identity, metric, ts] = number(value)
            if self.state == 'unavailable':
                return
            try:
                with self.db:
                    self.db.execute('DELETE FROM samples WHERE ts < ? OR ts > ?', (now-WINDOW, now))
                    self.db.execute('INSERT OR REPLACE INTO samples VALUES (?,?,?,?)', (identity,metric,ts,number(value)))
            except sqlite3.Error:
                self.state = 'unavailable'

    def rows(self, identity, metric, now):
        with self.lock:
            if self.state != 'unavailable':
                try:
                    with self.db:
                        self.db.execute('DELETE FROM samples WHERE ts < ? OR ts > ?', (now-WINDOW, now))
                        return self.db.execute('SELECT ts,value FROM samples WHERE identity=? AND metric=? ORDER BY ts', (identity,metric)).fetchall()
                except sqlite3.Error:
                    self.state = 'unavailable'
            self.memory = {k: v for k, v in self.memory.items() if now-WINDOW <= k[2] <= now}
            return sorted((ts, v) for (i, m, ts), v in self.memory.items() if i == identity and m == metric)


WINDOW = 1800
_STORE = None


class BackgroundRRD:
    """Bounded, single-flight optional reads; never hold a lock during I/O.

    Cold/missing data stays empty until a later collection. Failed refreshes keep
    real timestamped old data (chart trims it), with the same 60s retry cooldown.
    No queued work: a saturated pool defers other paths to the next collection.
    """
    def __init__(self, read=None, clock=time.monotonic):
        from concurrent.futures import ThreadPoolExecutor
        self.read = read
        self.clock = clock
        self.condition = threading.Condition()
        self.entries = {}
        self.inflight = set()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='guest-rrd')

    def __call__(self, path):
        with self.condition:
            now = self.clock()
            entry = self.entries.get(path)
            if (entry is None or now-entry[0] >= 60) and path not in self.inflight and len(self.inflight) < 2:
                self.inflight.add(path)
                self.executor.submit(self._refresh, path)
            return entry[1] if entry else []

    def _refresh(self, path):
        try:
            if self.read is None:
                import proxmox
                data = proxmox._api(path, allowed_rrd=frozenset([path]))
            else:
                data = self.read(path)
        except Exception:
            data = None
        with self.condition:
            old = self.entries.pop(path, (0, []))[1]
            self.entries[path] = (self.clock(), data if data is not None else old)
            while len(self.entries) > 128:
                del self.entries[next(iter(self.entries))]
            self.inflight.remove(path)
            self.condition.notify_all()


_RRD_CACHE = BackgroundRRD()


def enrich(result, api=None, store=None):
    """Attach graphs after the existing audited vm_metrics identity join."""
    import proxmox
    global _STORE
    if store is None:
        if _STORE is None:
            _STORE = Store(os.environ.get('WORKLOAD_HISTORY_PATH', ':memory:'))
        store = _STORE
    api = api or _RRD_CACHE
    now = time.time()
    for guest in result.get('guest_inventory') or []:
        kind, identity, node = guest.get('type'), guest.get('id'), guest.get('node')
        valid = kind in ('qemu','lxc') and type(identity) is int and identity > 0 and isinstance(node,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*',node)
        series = {'cpu': [], 'ram': [], 'disk': []}
        if valid and guest.get('status') == 'running':
            try:
                series = rrd(api(f'/nodes/{node}/{kind}/{identity}/rrddata?timeframe=hour&cf=AVERAGE'),kind)
            except Exception:
                pass
        graphs = {}
        for metric in series:
            source = 'PVE RRD · 1 min averages'
            points = series[metric]
            gap = 90
            if metric != 'cpu' and guest.get('memory_source' if metric == 'ram' else 'disk_source') == 'Komodo':
                source = 'Komodo / Periphery · collected samples'
                binding = guest.get('metric_binding')
                ts = guest.get('metric_sample_ts')
                points = []
                if valid and binding and number(ts) is not None:
                    key = f'{kind}/{identity}|{binding}'
                    value = (guest.get(metric) or {}).get('percent')
                    store.add(key,metric,ts,value,now)
                    points = store.rows(key,metric,now)
                gap = 30
            graphs[metric] = dict(chart(points,now,gap),source=source,persistence_state=store.state)
        guest['history'] = graphs
    return result


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def chart(points, now, gap=90):
    rows = sorted((t, number(v)) for t, v in points if number(t) is not None and now-WINDOW <= t <= now)
    scale = max([100] + [v for _, v in rows if v is not None])
    path, dots, previous = [], [], None
    for ts, value in rows:
        if value is None:
            previous = None
            continue
        x, y = 100*(ts-now+WINDOW)/WINDOW, 30*(1-value/scale)
        path.append(f"{'L' if previous is not None and ts-previous < gap else 'M'}{x:.3f},{y:.3f}")
        dots.append({'x': x, 'y': y})
        previous = ts
    # Close each existing line segment independently: nulls and time gaps remain empty.
    areas = []
    for segment in ' '.join(path).split('M')[1:]:
        first_x = segment.split(',')[0]
        last_x = segment.strip().split(' ')[-1].lstrip('L').split(',')[0]
        areas.append(f'M{segment.strip()} L{last_x},30.000 L{first_x},30.000 Z')
    return dict(path=' '.join(path), area_path=' '.join(areas), dots=dots, samples=len(dots), scale=scale,
                start=now-WINDOW, end=now, window_seconds=WINDOW,
                state='collecting' if len(dots)<2 else 'ready')


def rrd(rows, kind):
    result = {'cpu': [], 'ram': [], 'disk': []}
    for row in rows:
        ts = number(row.get('time'))
        if ts is None:
            continue
        cpu = number(row.get('cpu'))
        result['cpu'].append((ts, 100*cpu if cpu is not None and cpu <= 1 else None))
        for metric, used, total in [('ram','mem','maxmem'),('disk','disk','maxdisk')]:
            u, t = number(row.get(used)), number(row.get(total))
            value = 100*u/t if u is not None and t else None
            if metric == 'disk' and (kind != 'lxc' or (value is not None and value > 100)):
                value = None
            result[metric].append((ts,value))
    return result
