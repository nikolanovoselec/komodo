"""Continuous collection uses existing singleflight caches, never HTTP requests."""
import importlib.util
import threading
import time


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    assert predicate()


def test_scheduler_advances_without_http_and_stops():
    assert importlib.util.find_spec('telemetry') is not None, 'Lifecycle sampler is missing'
    from telemetry import Sampler
    samples = []
    sampler = Sampler([lambda: samples.append(time.monotonic())], interval=.01)
    assert samples == []  # construction/import never starts work
    sampler.start()
    try:
        wait_for(lambda: len(samples) >= 3)
    finally:
        sampler.stop()
    count = len(samples)
    time.sleep(.03)
    assert len(samples) == count
    assert not any(t.is_alive() for t in sampler.threads)


def test_failures_are_isolated_retried_and_never_logged(capsys):
    from telemetry import Sampler
    failed, healthy = [], []
    def fail():
        failed.append(1)
        raise RuntimeError('secret-token')
    sampler = Sampler([fail, lambda: healthy.append(1)], interval=.01)
    sampler.start()
    try:
        wait_for(lambda: len(healthy) >= 3)
        assert len(failed) >= 2
    finally:
        sampler.stop()
    captured = capsys.readouterr()
    assert 'secret-token' not in captured.out + captured.err


def test_server_opt_in_collects_without_requests_and_close_stops():
    import adapter
    samples, extra = [], []
    def load():
        samples.append(time.monotonic())
        return {'history': list(samples)}
    server = adapter.make_server(('127.0.0.1', 0), load,
                                 continuous=True, warmers=[lambda: extra.append(1)],
                                 sample_interval=.01)
    try:
        wait_for(lambda: len(samples) == 1 and len(extra) >= 2)
        # The real five-second TTL still owns the upstream cadence.
        time.sleep(.04)
        assert len(samples) == 1
        wait_for(lambda: len(samples) >= 2, timeout=6)
        assert samples[1] - samples[0] >= 5
    finally:
        server.server_close()
    counts = len(samples), len(extra)
    time.sleep(.03)
    assert (len(samples), len(extra)) == counts
    assert not any(t.is_alive() for t in server.sampler.threads)


def test_test_servers_do_not_sample_by_default():
    import adapter
    calls = []
    server = adapter.make_server(('127.0.0.1', 0), lambda: calls.append(1))
    try:
        time.sleep(.03)
        assert calls == []
    finally:
        server.server_close()


def test_production_main_enables_all_cache_warmers(monkeypatch):
    import adapter
    import media
    import types
    import sys
    calls = []
    for name, source in media.SOURCES.items():
        monkeypatch.setattr(source, 'snapshot', lambda name=name: calls.append(name))
    monkeypatch.setattr(adapter._pve_cache, 'snapshot', lambda: calls.append('pve'))
    monkeypatch.setenv('DYNACAT_UNIFI_TOKEN', 'not-a-real-credential')
    monkeypatch.setitem(sys.modules, 'unifi', types.SimpleNamespace(current=lambda: calls.append('unifi')))
    class FakeServer:
        def __enter__(self): return self
        def __exit__(self, *args): calls.append('closed')
        def serve_forever(self): calls.append('served')
    def make_server(address, loader, **kwargs):
        assert kwargs['continuous'] is True
        for callback in kwargs['warmers']:
            callback()
        return FakeServer()
    monkeypatch.setattr(adapter, 'make_server', make_server)
    assert hasattr(adapter, 'main'), 'Production lifecycle entrypoint is missing'
    adapter.main()
    assert set(calls) == set(media.SOURCES) | {'pve', 'unifi', 'served', 'closed'}


def test_shutdown_stops_sampler_and_blocked_flight_never_overlaps():
    import adapter
    entered, release = threading.Event(), threading.Event()
    calls, healthy = [], []
    def blocked():
        calls.append(1)
        entered.set()
        release.wait(3)
        return {'ok': True}
    server = adapter.make_server(('127.0.0.1', 0), blocked, continuous=True,
                                 warmers=[lambda: healthy.append(1)], sample_interval=.005)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        assert entered.wait(1)
        wait_for(lambda: len(healthy) >= 5)
        assert calls == [1]
        server.shutdown()
        assert not any(t.is_alive() for t in server.sampler.threads)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_fixed_workers_bound_blocked_hooks_and_stop_time():
    from telemetry import Sampler
    release, entered = threading.Event(), threading.Event()
    blocked_calls, healthy = [], []
    def blocked():
        blocked_calls.append(1)
        entered.set()
        release.wait(2)
    sampler = Sampler([blocked, lambda: healthy.append(1)], interval=.005)
    sampler.start()
    sampler.start()  # start is idempotent
    try:
        assert entered.wait(1)
        wait_for(lambda: len(healthy) >= 5)
        assert len(sampler.threads) == 2
        assert blocked_calls == [1]
        started = time.monotonic()
        sampler.stop(timeout=.03)
        assert time.monotonic() - started < .2
    finally:
        release.set()
        sampler.stop()
    assert not any(t.is_alive() for t in sampler.threads)


def test_real_media_cache_persists_graph_samples_without_http(tmp_path):
    from media import Source
    from media_traffic import TrafficHistory
    from telemetry import Sampler
    path = str(tmp_path / 'traffic.sqlite')
    history = TrafficHistory(storage_path=path)
    fetched = []
    def load():
        now = time.time()
        fetched.append(time.monotonic())
        return history.observe(dict(refresh_ts=now*1000, polling_rate='5-sec',
                                    network_ingress_bytes=1000, network_egress_bytes=2000), now=now)
    source = Source(load, .03, 30, 'Test media resources')
    sampler = Sampler([source.snapshot], interval=.005)
    sampler.start()
    try:
        wait_for(lambda: source.data is not None and source.data['graph']['samples'] >= 3)
        assert all(b-a >= .03 for a, b in zip(fetched, fetched[1:]))
        restored = TrafficHistory(storage_path=path)
        assert len(restored.points) >= 3
        assert source.data['warmup'] is False
    finally:
        sampler.stop()


def test_main_without_optional_unifi_credentials(monkeypatch):
    import adapter
    import media
    calls = []
    monkeypatch.delenv('DYNACAT_UNIFI_TOKEN', raising=False)
    class FakeServer:
        def __enter__(self): return self
        def __exit__(self, *args): calls.append('closed')
        def serve_forever(self): calls.append('served')
    def make_server(address, loader, **kwargs):
        assert kwargs['continuous'] is True
        assert len(kwargs['warmers']) == 1 + len(media.SOURCES)
        return FakeServer()
    monkeypatch.setattr(adapter, 'make_server', make_server)
    adapter.main()
    assert calls == ['served', 'closed']
