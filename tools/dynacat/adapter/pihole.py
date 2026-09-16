"""Bounded read-only Pi-hole v6 projection; credentials remain server-side."""
from datetime import datetime, timezone
import math

NAMES = ('pihole-master.lan', 'pihole-slave.lan')
METRICS = ('total_queries', 'blocked_queries', 'gravity_entries')


def query_history(rows, now):
    start = now - 1800
    maps = []
    for row in rows:
        data = {}
        for r in row.get('history') or []:
            if not isinstance(r, dict) or type(r.get('timestamp')) is not int:
                continue
            valid = all(type(r.get(k)) is int and r[k] >= 0 for k in ('total','blocked'))
            data[r['timestamp']] = r if valid and r['blocked'] <= r['total'] else None
        maps.append(data)
    stamps = sorted({t for data in maps for t in data if start <= t <= now})
    truncated = len(stamps) > 181
    stamps = stamps[-181:]
    points = []
    for stamp in stamps:
        records = [data[stamp] for data in maps if data.get(stamp) is not None]
        complete = len(records) == len(NAMES)
        points.append(dict(timestamp=stamp, available_instances=len(records),
                           total=sum(r['total'] for r in records) if complete else None,
                           permitted=sum(r['total']-r['blocked'] for r in records) if complete else None,
                           blocked=sum(r['blocked'] for r in records) if complete else None))
    maximum = max([p[k] for p in points for k in ('permitted','blocked') if p[k] is not None] or [0])
    maximum_total = max([p['permitted'] + p['blocked'] for p in points if p['permitted'] is not None] or [0])
    for point in points:
        point['label'] = datetime.fromtimestamp(point['timestamp'], timezone.utc).strftime('%H:%M')
        for key in ('permitted', 'blocked'):
            point[key + '_percent'] = point[key] / max(maximum_total, 1) * 100 if point[key] is not None else None
    result = dict(available=any(p['permitted'] is not None for p in points),
                  max_total_count=maximum_total,
                  partial=truncated or any(p['permitted'] is None for p in points) or len(points) < 3 or any(b-a > 600 for a,b in zip(stamps, stamps[1:])),
                  interval_seconds=600, window_seconds=1800, start=datetime.fromtimestamp(start, timezone.utc).strftime('%H:%M'), end=datetime.fromtimestamp(now, timezone.utc).strftime('%H:%M'),
                  max_count=maximum, points=points, error=None)
    for key in ('total', 'permitted', 'blocked'):
        # Keep the permitted legacy scale; request and block charts scale independently.
        series_maximum = maximum if key == 'permitted' else max([p[key] for p in points if p[key] is not None] or [0])
        segments, segment = [], []
        previous = None
        for p in points:
            if p[key] is None or (previous is not None and p['timestamp']-previous > 600):
                if segment: segments.append(segment)
                segment=[]
            if p[key] is not None:
                segment.append(((p['timestamp']-start)/1800*600,140-p[key]/max(series_maximum,1)*140))
            previous=p['timestamp']
        if segment: segments.append(segment)
        paths = ['M'+' L'.join(f'{x:.2f},{y:.2f}' for x,y in seg) for seg in segments]
        result[key] = dict(max_count=series_maximum, path=' '.join(paths), area_path=' '.join(path+f' L{seg[-1][0]:.2f},140 L{seg[0][0]:.2f},140 Z' for path,seg in zip(paths,segments)))
    return result


def collect(fetch, now=None):
    rows, instances = [], []
    for name in NAMES:
        try:
            row = fetch(name)
            if any(type(row[key]) is not int or row[key] < 0 for key in METRICS):
                raise ValueError('Pi-hole metrics unavailable')
            rows.append(row)
            instances.append(dict(name=name, available=True,
                                  configured_upstreams=row.get('configured_upstreams'),
                                  upstreams_available=row.get('configured_upstreams') is not None,
                                  upstreams_error=row.get('upstreams_error'),
                                  upstreams_truncated=row.get('upstreams_truncated', False)))
        except Exception:
            instances.append(dict(name=name, available=False, configured_upstreams=None,
                                  upstreams_available=False, upstreams_error='Configured upstream DNS unavailable.',
                                  upstreams_truncated=False,
                                  error='Pi-hole unavailable; verify TLS, network and API authentication.'))
    partial = 0 < len(rows) < len(NAMES)
    return dict(available=bool(rows), partial=partial, gravity_aggregation='sum_not_deduplicated',
                error=('Partial Pi-hole data; sums cover available instances only.' if partial else
                       'Pi-hole unavailable; verify TLS, network and API authentication.' if not rows else None),
                instances=instances, query_history=query_history(rows, time.time() if now is None else now),
                **{key: sum(row[key] for row in rows) if rows else None for key in METRICS})


import hashlib
import hmac
import http.client
import json
import ssl
from urllib.parse import urlsplit


def request(url, pin, method, path, *, password=None, sid=None, connection_factory=None):
    target = urlsplit(url)
    if target.scheme != 'https' or not target.hostname or target.username or target.password or target.path not in ('', '/') or target.query or target.fragment:
        raise ValueError('Invalid Pi-hole HTTPS origin')
    if len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin):
        raise ValueError('Invalid certificate pin')
    # Self-signed endpoints: leaf SHA256 pin is the trust anchor, checked before
    # EVERY HTTP request (including credentials and logout), never a fallback.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    conn = (connection_factory or http.client.HTTPSConnection)(target.hostname, target.port or 443, timeout=3, context=context)
    try:
        conn.connect()
        digest = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
        if not hmac.compare_digest(digest, pin):
            raise ValueError('Pi-hole certificate pin mismatch')
        headers = {'Content-Type': 'application/json', 'Connection': 'close'}
        if sid:
            headers['sid'] = sid
        body = json.dumps({'password': password}).encode() if password is not None else None
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError('Pi-hole response too large')
        if response.status == 204:
            return None
        if response.status != 200:
            raise ValueError('Pi-hole response unavailable')
        return json.loads(raw)
    finally:
        conn.close()


import os

DEFAULTS = {
    NAMES[0]: ('MASTER', 'https://192.168.5.162', '7a8781221bacca29595dbf15a50d45e106f75ced401c2ad517afe1065f5f35e3'),
    NAMES[1]: ('SLAVE', 'https://192.168.5.92', 'cce882a1dc716514855827507d1253dfa4a51ad2f027b0e1c34d6441fd071f41'),
}


def fetch_instance(name, transport=None):
    transport = transport or request
    role, url, pin = DEFAULTS[name]
    url = os.environ.get('PIHOLE_' + role + '_URL', url)
    pin = os.environ.get('PIHOLE_' + role + '_SHA256', pin)
    password = os.environ['PIHOLE_API_KEY']
    if not password:
        raise ValueError('Pi-hole credential unavailable')
    session = transport(url, pin, 'POST', '/api/auth', password=password)['session']
    sid = session['sid']
    try:
        if not session.get('valid') or not isinstance(sid, str) or not sid:
            raise ValueError('Pi-hole authentication unavailable')
        summary = transport(url, pin, 'GET', '/api/stats/summary', sid=sid)
        history = transport(url, pin, 'GET', '/api/history', sid=sid)
        upstreams_error = None
        try:
            upstreams = transport(url, pin, 'GET', '/api/config/dns/upstreams', sid=sid)['config']['dns']['upstreams']
            if not isinstance(upstreams, list) or any(not isinstance(v, str) or not 1 <= len(v) <= 256 or not v.isprintable() for v in upstreams):
                raise ValueError('Invalid upstream list')
        except Exception:
            upstreams = None
            upstreams_error = 'Configured upstream DNS unavailable.'
        return dict(total_queries=summary['queries']['total'], blocked_queries=summary['queries']['blocked'],
                    gravity_entries=summary['gravity']['domains_being_blocked'],
                    history=history['history'], configured_upstreams=upstreams[:16] if upstreams is not None else None,
                    upstreams_error=upstreams_error, upstreams_truncated=upstreams is not None and len(upstreams) > 16)
    finally:
        if isinstance(sid, str) and sid:
            transport(url, pin, 'DELETE', '/api/auth', sid=sid)


import copy
import threading
import time


def unavailable():
    def missing(name):
        raise ValueError('unavailable')
    return collect(missing)


class Snapshot:
    """Single-flight cache warmed by the server lifecycle, with atomic disk snapshots.

    Reads never perform upstream/disk I/O. Retry 10s after completion; health
    expires 30s after collection start. Persist only the bounded public projection.
    """
    def __init__(self, loader=None, clock=None, storage_path=None):
        self.loader = loader or (lambda: collect(fetch_instance))
        self.clock = clock or time.monotonic
        self.storage_path = storage_path
        self.lock = threading.Lock()
        self.worker = None
        self.data = None
        self.started = self.completed = None
        if storage_path:
            try:
                with open(storage_path, 'rb') as stream:
                    raw = stream.read(262145)
                if len(raw) > 262144:
                    raise ValueError('Snapshot too large')
                saved = json.loads(raw)
                age = time.time() - saved['started_at']
                if saved['version'] != 1 or not math.isfinite(age) or age < 0:
                    raise ValueError('Invalid snapshot')
                data = saved['data']
                template = unavailable()
                if (not isinstance(data, dict) or set(data) != set(template) | {'fetched_at'}
                        or type(data['available']) is not bool or type(data['partial']) is not bool
                        or not isinstance(data['fetched_at'], (int, float))
                        or not isinstance(data['query_history'], dict)
                        or set(data['query_history']) != set(template['query_history']) | {'fetched_at', 'stale'}
                        or not isinstance(data['query_history']['points'], list)
                        or len(data['query_history']['points']) > 181
                        or not isinstance(data['instances'], list) or len(data['instances']) != len(NAMES)):
                    raise ValueError('Invalid projection')
                self.data = data
                self.started = self.clock() - age
            except (OSError, ValueError, KeyError, TypeError):
                self.data = None

    def _persist(self, data, started):
        if not self.storage_path:
            return
        temporary = self.storage_path + '.tmp'
        try:
            payload = json.dumps(dict(version=1, started_at=time.time() - (self.clock()-started), data=data), allow_nan=False).encode()
            if len(payload) > 262144:
                raise ValueError('Snapshot too large')
            with open(temporary, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.storage_path)
        except (OSError, ValueError, TypeError):
            # Persistence failure must not suppress live telemetry or leak secrets.
            try:
                os.unlink(temporary)
            except OSError:
                pass

    def _refresh(self, started):
        try:
            data = self.loader()
        except Exception:
            data = unavailable()
        data['fetched_at'] = time.time()
        data['query_history'].update(fetched_at=data['fetched_at'], stale=False)
        with self.lock:
            if not data['query_history']['available'] and self.data is not None:
                data['query_history'] = copy.deepcopy(self.data['query_history'])
                data['query_history'].update(stale=True, partial=True)
            self.data, self.started, self.completed = data, started, self.clock()
        self._persist(data, started)

    def current(self):
        with self.lock:
            now = self.clock()
            if (self.worker is None or not self.worker.is_alive()) and (self.completed is None or now - self.completed >= 10):
                self.worker = threading.Thread(target=self._refresh, args=(now,), daemon=True)
                self.worker.start()
            age = None if self.started is None else max(0, now - self.started)
            stale = age is not None and age >= 30
            result = copy.deepcopy(self.data) if self.data is not None else unavailable()
            if stale:
                history = result['query_history']
                result = unavailable()
                result['query_history'] = history
                history.update(stale=True, partial=True)
                result['fetched_at'] = self.data.get('fetched_at')
            result.setdefault('fetched_at', None)
            result['freshness'] = dict(state='starting' if self.data is None else 'stale' if stale else 'unavailable' if not result['available'] else 'partial' if result['partial'] else 'cached',
                age_seconds=age, max_age_seconds=30, collecting=self.worker.is_alive(),
                age_basis='collection_started', fetched_at_basis='collection_completed_not_source_sample')
            return result


_snapshot = Snapshot(storage_path=os.environ.get('PIHOLE_HISTORY_PATH'))


def current():
    return _snapshot.current()
