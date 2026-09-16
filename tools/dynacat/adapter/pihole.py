"""Bounded read-only Pi-hole v6 projection; credentials remain server-side."""
from datetime import datetime, timezone
import math

PERMITTED = frozenset({'FORWARDED', 'CACHE', 'CACHE_STALE', 'RETRIED', 'RETRIED_DNSSEC', 'IN_PROGRESS'})
BLOCKED = frozenset({'GRAVITY', 'REGEX', 'DENYLIST', 'EXTERNAL_BLOCKED_IP',
                     'EXTERNAL_BLOCKED_NULL', 'EXTERNAL_BLOCKED_NXRA', 'EXTERNAL_BLOCKED_EDE15',
                     'GRAVITY_CNAME', 'REGEX_CNAME', 'DENYLIST_CNAME', 'DBBUSY', 'SPECIAL_DOMAIN'})
NAMES = ('pihole-master.lan', 'pihole-slave.lan')
METRICS = ('total_queries', 'blocked_queries', 'gravity_entries')


def history(records, name, statuses):
    out = []
    for record in records:
        try:
            stamp = record['time']
            domain, status = record['domain'], record['status']
            if (status not in statuses or not isinstance(domain, str) or not 0 < len(domain) <= 253
                    or isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp)):
                continue
            out.append(dict(domain=domain, status=status, timestamp=stamp,
                            time=datetime.fromtimestamp(stamp, timezone.utc).isoformat(), instance=name))
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
    return out


def collect(fetch):
    rows, instances = [], []
    histories = {'recent_permitted': [], 'recent_blocked': []}
    for name in NAMES:
        try:
            row = fetch(name)
            if any(type(row[key]) is not int or row[key] < 0 for key in METRICS):
                raise ValueError('Pi-hole metrics unavailable')
            if not all(isinstance(row[key], list) for key in histories):
                raise ValueError('Pi-hole history unavailable')
            permitted = history(row['recent_permitted'], name, PERMITTED)
            blocked = history(row['recent_blocked'], name, BLOCKED)
            histories['recent_permitted'].extend(permitted)
            histories['recent_blocked'].extend(blocked)
            rows.append(row)
            instances.append(dict(name=name, available=True))
        except Exception:
            instances.append(dict(name=name, available=False, error='Pi-hole unavailable; verify TLS, network and API authentication.'))
    partial = 0 < len(rows) < len(NAMES)
    return dict(available=bool(rows), partial=partial, gravity_aggregation='sum_not_deduplicated',
                error=('Partial Pi-hole data; sums cover available instances only.' if partial else
                       'Pi-hole unavailable; verify TLS, network and API authentication.' if not rows else None),
                instances=instances,
                **{key: sorted(items, key=lambda item: item['timestamp'], reverse=True)[:10] for key, items in histories.items()},
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
        permitted = transport(url, pin, 'GET', '/api/queries?length=10&upstream=permitted', sid=sid)
        blocked = transport(url, pin, 'GET', '/api/queries?length=10&upstream=blocklist', sid=sid)
        return dict(total_queries=summary['queries']['total'], blocked_queries=summary['queries']['blocked'],
                    gravity_entries=summary['gravity']['domains_being_blocked'],
                    recent_permitted=permitted['queries'], recent_blocked=blocked['queries'])
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
    """Single-flight async demand cache: 10s retry, 30s max sample age."""
    def __init__(self, loader=None, clock=None):
        self.loader = loader or (lambda: collect(fetch_instance))
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.worker = None
        self.data = None
        self.started = self.completed = None

    def _refresh(self, started):
        try:
            data = self.loader()
        except Exception:
            data = unavailable()
        with self.lock:
            self.data, self.started, self.completed = data, started, self.clock()

    def current(self):
        with self.lock:
            now = self.clock()
            if (self.worker is None or not self.worker.is_alive()) and (self.completed is None or now - self.completed >= 10):
                self.worker = threading.Thread(target=self._refresh, args=(now,), daemon=True)
                self.worker.start()
            if self.data is None or now - self.started >= 30:
                return unavailable()
            return copy.deepcopy(self.data)


_snapshot = Snapshot()


def current():
    return _snapshot.current()
