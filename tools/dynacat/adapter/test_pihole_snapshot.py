"""Precollected Pi-hole reads, lifecycle sampling and bounded restart history."""
import json
import threading
import time
import pytest

import pihole


@pytest.mark.parametrize('data', [None, {}, {'available': True, 'query_history': None}])
def test_invalid_persisted_projection_is_ignored(tmp_path, data):
    path = tmp_path / 'pihole.json'
    path.write_text(json.dumps(dict(version=1, started_at=time.time(), data=data)))
    cache = pihole.Snapshot(sample, storage_path=str(path))
    assert cache.data is None


def test_no_view_sampler_refreshes_and_persists_without_requests(tmp_path):
    import adapter
    from test_telemetry import wait_for
    clock, calls = [0], []
    path = tmp_path / 'pihole.json'
    def load():
        calls.append(1)
        return sample(1800 + len(calls))
    cache = pihole.Snapshot(load, clock=lambda: clock[0], storage_path=str(path))
    server = adapter.make_server(('127.0.0.1', 0), lambda: {}, continuous=True,
                                 warmers=[cache.current], sample_interval=.005)
    try:
        wait_for(lambda: path.exists())
        clock[0] = 11
        wait_for(lambda: len(calls) == 2)
        cache.worker.join(1)
        restored = pihole.Snapshot(sample, storage_path=str(path))
        assert restored.data['query_history']['points'][-1]['timestamp'] == 1802
    finally:
        server.server_close()
    clock[0] = 22
    time.sleep(.03)
    assert len(calls) == 2


def test_persistence_failure_does_not_break_live_reads(tmp_path):
    cache = pihole.Snapshot(sample, storage_path=str(tmp_path / 'missing' / 'pihole.json'))
    cache.current()
    cache.worker.join(1)
    assert cache.current()['total_queries'] == 40


def test_expired_restart_is_not_reported_as_live(tmp_path):
    path = tmp_path / 'pihole.json'
    cache = pihole.Snapshot(sample, storage_path=str(path))
    cache.current()
    cache.worker.join(1)
    saved = json.loads(path.read_text())
    saved['started_at'] -= 60
    path.write_text(json.dumps(saved))
    gate = threading.Event()
    def blocked():
        gate.wait(2)
        return sample()
    restored = pihole.Snapshot(blocked, storage_path=str(path))
    try:
        result = restored.current()
        assert not result['available']
        assert result['freshness']['state'] == 'stale'
        assert result['query_history']['stale']
        assert result['query_history']['points']
    finally:
        gate.set()
        restored.worker.join(1)


def test_network_first_read_never_waits_for_pihole_upstream(monkeypatch):
    import adapter
    import unifi
    import urllib.request
    gate = threading.Event()
    calls = []
    def blocked():
        calls.append(1)
        gate.wait(2)
        return sample()
    cache = pihole.Snapshot(blocked)
    monkeypatch.setattr(pihole, '_snapshot', cache)
    monkeypatch.setattr(unifi, 'current', lambda: {'state': 'available'})
    server = adapter.make_server(('127.0.0.1', 0), lambda: {})
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for _ in range(3):
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/network-current', timeout=.3) as response:
                data = json.load(response)['pihole']
                assert data['freshness']['state'] == 'starting'
                assert data['total_queries'] is None
        assert calls == [1]
    finally:
        gate.set()
        cache.worker.join(1)
        server.shutdown()
        server.server_close()
        worker.join(1)


def test_disk_projection_excludes_query_domains_and_credentials(tmp_path):
    path = tmp_path / 'pihole.json'
    def load():
        return pihole.collect(lambda name: dict(total_queries=20, blocked_queries=3,
            gravity_entries=100, history=[], domains=['PRIVATE-DOMAIN'], password='SECRET', sid='SID'))
    cache = pihole.Snapshot(load, storage_path=str(path))
    cache.current()
    cache.worker.join(1)
    raw = path.read_text()
    assert all(value not in raw for value in ('PRIVATE-DOMAIN', 'SECRET', 'SID', 'password'))


def test_history_is_bounded_even_with_dense_upstream_rows():
    rows = [dict(history=[dict(timestamp=t, total=20, blocked=3) for t in range(2000)])] * 2
    result = pihole.query_history(rows, 2000)
    assert len(result['points']) <= 181
    assert result['points'][-1]['timestamp'] == 1999
    assert result['partial'] is True


def sample(now=1800):
    return pihole.collect(lambda name: dict(total_queries=20, blocked_queries=3,
        gravity_entries=100, history=[dict(timestamp=now, total=20, blocked=3)]), now=now)


def test_restart_reads_persisted_snapshot_before_blocked_upstream(tmp_path):
    path = tmp_path / 'pihole.json'
    cache = pihole.Snapshot(sample, storage_path=str(path))
    cache.current()
    cache.worker.join(1)
    original = cache.current()
    assert path.stat().st_size < 262144
    gate = threading.Event()
    calls = []
    def blocked():
        calls.append(1)
        gate.wait(2)
        return sample()
    restored = pihole.Snapshot(blocked, storage_path=str(path))
    try:
        started = time.monotonic()
        for _ in range(20):
            result = restored.current()
            assert result['query_history']['points'] == original['query_history']['points']
            assert result['fetched_at'] == original['fetched_at']
        assert time.monotonic() - started < .2
        assert len(calls) == 1
    finally:
        gate.set()
        restored.worker.join(1)


def test_failed_refresh_preserves_last_history_as_stale(tmp_path):
    clock = [0]
    cache = pihole.Snapshot(sample, clock=lambda: clock[0], storage_path=str(tmp_path / 'pihole.json'))
    cache.current()
    cache.worker.join(1)
    original = cache.current()
    cache.loader = pihole.unavailable
    clock[0] = 11
    cache.current()
    cache.worker.join(1)
    failed = cache.current()
    assert not failed['available']
    assert failed['freshness']['state'] == 'unavailable'
    assert failed['query_history']['points'] == original['query_history']['points']
    assert failed['query_history']['stale']
    assert failed['query_history']['fetched_at'] == original['fetched_at']


def test_stale_snapshot_keeps_timestamped_history_without_healthy_counters():
    clock = [0]
    gate = threading.Event()
    gate.set()
    def load():
        gate.wait(2)
        return sample()
    cache = pihole.Snapshot(load, clock=lambda: clock[0])
    cache.current()
    cache.worker.join(1)
    fresh = cache.current()
    assert fresh['freshness']['state'] == 'cached'
    assert fresh['freshness']['age_seconds'] == 0
    assert fresh['fetched_at'] is not None
    clock[0] = 31
    gate.clear()
    try:
        started = time.monotonic()
        stale = cache.current()
        assert time.monotonic() - started < .1
        assert not stale['available'] and stale['total_queries'] is None
        assert stale['freshness']['state'] == 'stale'
        assert stale['fetched_at'] == fresh['fetched_at']
        assert stale['query_history']['points'] == fresh['query_history']['points']
        assert stale['query_history']['stale'] is True
        assert stale['query_history']['partial'] is True
    finally:
        gate.set()
        cache.worker.join(1)
