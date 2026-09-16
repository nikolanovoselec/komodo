import importlib
import json
import pytest


def module():
    return importlib.import_module('pihole')


def source(name):
    return dict(total_queries=20, blocked_queries=3, gravity_entries=100,
                recent_permitted=[], recent_blocked=[])


@pytest.mark.parametrize('failed', [1, 2])
def test_failed_instances_are_not_zero_or_secret_errors(failed):
    def fetch(name):
        if name == 'pihole-slave.lan' or failed == 2:
            raise TimeoutError('PASSWORD SID CLIENT SECRET')
        return source(name)
    r = module().collect(fetch)
    assert r['available'] is (failed == 1)
    assert r['partial'] is (failed == 1)
    assert r['total_queries'] == (20 if failed == 1 else None)
    assert 'SECRET' not in json.dumps(r)
    assert r['error']


def test_history_whitelist_privacy_sorting_and_latest_ten():
    def fetch(name):
        r = source(name)
        r['recent_permitted'] = [dict(domain='example.org', time=i + (0.5 if 'slave' in name else 0), status=s, client={'ip':'PRIVATE'}, sid='SECRET') for i,s in enumerate(['CACHE', 'FORWARDED', 'CACHE_STALE', 'RETRIED', 'RETRIED_DNSSEC', 'IN_PROGRESS', 'UNKNOWN', 'GRAVITY'] * 3)]
        r['recent_blocked'] = [dict(domain='ads.example', time=i, status='GRAVITY', client='PRIVATE') for i in range(12)]
        return r
    r = module().collect(fetch)
    for key in ('recent_permitted', 'recent_blocked'):
        assert len(r[key]) == 10
        assert [x['timestamp'] for x in r[key]] == sorted([x['timestamp'] for x in r[key]], reverse=True)
        assert all(set(x) == {'domain', 'timestamp', 'time', 'status', 'instance'} for x in r[key])
    assert {x['status'] for x in r['recent_permitted']} <= {'CACHE', 'FORWARDED', 'CACHE_STALE', 'RETRIED', 'RETRIED_DNSSEC', 'IN_PROGRESS'}
    assert {'pihole-master.lan','pihole-slave.lan'} == {x['instance'] for x in r['recent_permitted']}
    assert 'SECRET' not in json.dumps(r) and 'PRIVATE' not in json.dumps(r)


def test_merge_sums_are_explicitly_not_deduplicated():
    p = module()
    r = p.collect(source)
    assert r['available'] and not r['partial']
    assert (r['total_queries'], r['blocked_queries'], r['gravity_entries']) == (40, 6, 200)
    assert r['gravity_aggregation'] == 'sum_not_deduplicated'
    assert [i['name'] for i in r['instances']] == ['pihole-master.lan', 'pihole-slave.lan']


def test_pinned_transport_rejects_before_sending_any_credentials():
    p = module()
    class Socket:
        def getpeercert(self, binary_form): return b'wrong certificate'
    class Connection:
        sock = Socket()
        closed = False
        def connect(self): pass
        def request(self, *a, **kw): pytest.fail('credentials sent before pin verified')
        def close(self): self.closed = True
    conn = Connection()
    with pytest.raises(ValueError, match='certificate'):
        p.request('https://192.168.5.162', 'a'*64, 'POST', '/api/auth',
                  password='SECRET', connection_factory=lambda *a, **kw: conn)
    assert conn.closed


@pytest.mark.parametrize('oversized', [False, True])
def test_transport_bounds_and_auth_only_after_pin(oversized):
    import hashlib
    p = module()
    events = []
    class Socket:
        def getpeercert(self, binary_form):
            events.append('pin')
            return b'cert'
    class Response:
        status = 200
        def read(self, size):
            assert size == 262145
            return b'x'*size if oversized else b'{"ok":true}'
    class Connection:
        sock = Socket()
        def connect(self): events.append('connect')
        def request(self, method, path, body, headers):
            assert events == ['connect', 'pin']
            assert json.loads(body) == {'password':'SECRET'}
            events.append('request')
        def getresponse(self): return Response()
        def close(self): events.append('close')
    def factory(*a, **kw):
        assert kw['timeout'] == 3
        return Connection()
    args = ('https://192.168.5.162', hashlib.sha256(b'cert').hexdigest(), 'POST', '/api/auth')
    if oversized:
        with pytest.raises(ValueError, match='response'):
            p.request(*args, password='SECRET', connection_factory=factory)
    else:
        assert p.request(*args, password='SECRET', connection_factory=factory) == {'ok':True}
    assert events[-1] == 'close'


@pytest.mark.parametrize('fail', [False, True])
def test_v6_session_logs_out_even_after_timeout(monkeypatch, fail):
    p = module()
    monkeypatch.setenv('PIHOLE_API_KEY', 'SECRET')
    calls = []
    def request(url, pin, method, path, **kw):
        calls.append((method,path))
        if method == 'POST':
            assert kw == {'password':'SECRET'}
            return {'session':{'sid':'SID', 'valid':True}}
        assert kw == {'sid':'SID'}
        if method == 'DELETE': return None
        if fail: raise TimeoutError('SECRET')
        if path == '/api/stats/summary':
            return {'queries':{'total':20,'blocked':3}, 'gravity':{'domains_being_blocked':100}}
        return {'queries':[]}
    if fail:
        with pytest.raises(TimeoutError): p.fetch_instance(p.NAMES[0], transport=request)
    else:
        assert p.fetch_instance(p.NAMES[0], transport=request) == source('master')
    assert calls[-1] == ('DELETE','/api/auth')


def test_cache_is_nonblocking_singleflight_expires_without_stale_health():
    import threading
    import time
    p = module()
    gate = threading.Event()
    calls = []
    clock = [0]
    def loader():
        calls.append(1)
        gate.wait(1)
        return p.collect(source)
    cache = p.Snapshot(loader, clock=lambda: clock[0])
    for _ in range(20):
        r = cache.current()
        assert not r['available'] and r['total_queries'] is None
    assert len(calls) == 1
    gate.set()
    cache.worker.join(1)
    assert cache.current()['total_queries'] == 40
    r = cache.current()
    r['instances'].clear()
    assert len(cache.current()['instances']) == 2
    assert len(calls) == 1
    clock[0] = 31
    gate.clear()
    assert cache.current()['available'] is False
    gate.set()
    cache.worker.join(1)


def test_network_endpoint_contains_independent_pihole_projection(monkeypatch):
    import adapter
    import unifi
    import threading
    import urllib.request
    monkeypatch.setattr(unifi, 'current', lambda: {'state':'available'})
    monkeypatch.setattr(module(), 'current', lambda: {'available':True,'total_queries':40})
    server = adapter.make_server(('127.0.0.1',0), lambda: {})
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/network-current',timeout=1) as response:
            assert json.load(response)['pihole']['total_queries'] == 40
    finally:
        server.shutdown()
        server.server_close()
        worker.join(1)


@pytest.mark.parametrize('value', [None, -1, True, '42', float('nan')])
def test_invalid_metrics_fail_instance_closed(value):
    def fetch(name):
        r = source(name)
        r['total_queries'] = value
        return r
    r = module().collect(fetch)
    assert not r['available']
    assert r['total_queries'] is None
    assert r['recent_permitted'] == []


def test_malformed_history_cannot_leak_from_failed_instance():
    def fetch(name):
        r = source(name)
        r['recent_permitted'] = [{'domain':'example.org', 'time':1, 'status':'CACHE'}]
        r['recent_blocked'] = None
        return r
    r = module().collect(fetch)
    assert not r['available']
    assert r['recent_permitted'] == []


def test_v6_external_ede15_is_blocked_not_permitted():
    p = module()
    record = {'domain':'ads.example', 'time':1, 'status':'EXTERNAL_BLOCKED_EDE15'}
    assert len(p.history([record], p.NAMES[0], p.BLOCKED)) == 1
    assert p.history([record], p.NAMES[0], p.PERMITTED) == []
