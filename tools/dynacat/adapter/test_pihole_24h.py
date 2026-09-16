"""24-hour contract tests; source fixtures here are explicitly synthetic."""
import json
import time
import pytest
import pihole


def full_day(now=172800):
    return [dict(timestamp=t, total=10+i, blocked=i % 9)
            for i,t in enumerate(range(now-86400+300, now, 600))]


def test_full_day_source_bins_map_exactly_to_full_width(monkeypatch):
    monkeypatch.setenv('PIHOLE_API_KEY', 'test-only')
    calls = []
    source = full_day()
    def transport(url, pin, method, path, **kw):
        calls.append(path)
        if method == 'POST': return {'session': {'valid': True, 'sid': 'test'}}
        if method == 'DELETE': return None
        if path == '/api/stats/summary':
            return {'queries': {'total': 20, 'blocked': 3}, 'gravity': {'domains_being_blocked': 100}}
        if path == '/api/config/dns/upstreams': return {'config': {'dns': {'upstreams': []}}}
        assert path == '/api/history'
        return {'history': source}
    result = pihole.collect(lambda name: pihole.fetch_instance(name, transport), now=172800)
    h = result['query_history']
    assert h['window_seconds'] == 86400
    assert h['end_epoch']-h['start_epoch'] == 86400
    assert h['interval_seconds'] == 600
    assert len(h['bins']) == 144
    assert not h['partial'] and not h['missing_spans']
    assert h['coverage_start_epoch'] == 86400 and h['coverage_end_epoch'] == 172800
    assert [(b['timestamp'],b['total'],b['blocked']) for b in h['bins']] == [(r['timestamp'],2*r['total'],2*r['blocked']) for r in source]
    assert h['total']['curve_path'].startswith('M0.000000,')
    assert h['total']['curve_path'].split()[-1].startswith('600.000000,')
    assert calls.count('/api/history') == 2


def test_day_endpoints_include_distinct_dates():
    h = pihole.query_history([{'history':full_day()}]*2, 172800)
    assert h['start'] == '02 Jan 00:00'
    assert h['end'] == '03 Jan 00:00'
    old = pihole.query_history([{'history':full_day()}]*2, 172800, window_seconds=1800)
    restored = pihole.migrate_snapshot({'instances':[], 'query_history':old})['query_history']
    assert restored['start'] == '02 Jan 00:00'
    assert restored['end'] == '03 Jan 00:00'


def test_aggregate_upstreams_canonical_dedup_without_dns(monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a: (_ for _ in ()).throw(AssertionError('No DNS')))
    lists = [['1.1.1.1', '2001:0db8:0000::1#0053', '1.1.1.1#5353', 'dns.example', '999.1.1.1', '1.1.1.1#0'],
             ['2001:db8::1#53', '1.1.1.1', '1.1.1.1#53', '1.1.1.1#5353']]
    def fetch(name):
        return dict(total_queries=20, blocked_queries=3, gravity_entries=100,
                    configured_upstreams=lists[pihole.NAMES.index(name)], history=[])
    result = pihole.collect(fetch, now=172800)
    assert result['configured_upstreams'] == ['1.1.1.1', '2001:db8::1#53', '1.1.1.1#5353', '1.1.1.1#53']
    assert result['upstreams_available'] is True
    assert result['upstreams_truncated'] is False
    assert result['gravity_entries'] == 200 and result['gravity_aggregation'] == 'sum_not_deduplicated'


def test_legacy_snapshot_migrates_short_history_as_gap_without_discard(tmp_path):
    source = full_day()[-3:]
    data = pihole.collect(lambda name: dict(total_queries=20, blocked_queries=3, gravity_entries=100,
        history=source, configured_upstreams=['1.1.1.1']), now=172800)
    for key in ('configured_upstreams', 'upstreams_available', 'upstreams_partial', 'upstreams_truncated'):
        data.pop(key, None)
    old = pihole.query_history([{'history': source}]*2, 172800, window_seconds=1800)
    old.update(fetched_at=172800, stale=False)
    data.update(query_history=old, fetched_at=172800)
    path = tmp_path/'pihole.json'
    path.write_text(json.dumps(dict(version=1, started_at=time.time()-60, data=data)))
    restored = pihole.Snapshot(storage_path=str(path))
    assert restored.data is not None
    h = restored.data['query_history']
    assert h['window_seconds'] == 86400
    assert h['partial'] and h['stale']
    assert h['fetched_at'] == 172800
    assert [(b['timestamp'], b['total']) for b in h['bins']] == [(b['timestamp'], b['total']) for b in old['bins']]
    assert h['missing_spans'] == [dict(start_epoch=86400, end_epoch=171000, x=0.0, width=587.5)]
    assert h['total']['curve_path'].startswith('M587.500000,')
    assert restored.data['configured_upstreams'] == ['1.1.1.1']
    assert restored.clock()-restored.started >= 60


@pytest.mark.parametrize('window_seconds', [1800, 86400])
def test_prior_snapshots_restore_upstream_partial_from_instances(tmp_path, window_seconds):
    source = full_day()[-3:]
    data = pihole.collect(lambda name: dict(total_queries=20, blocked_queries=3, gravity_entries=100,
        history=source, configured_upstreams=['1.1.1.1'] if name == pihole.NAMES[0] else None), now=172800)
    data.pop('upstreams_partial')
    if window_seconds == 1800:
        for key in ('configured_upstreams', 'upstreams_available', 'upstreams_truncated'):
            data.pop(key)
    data['query_history'] = pihole.query_history([{'history': source}]*2, 172800, window_seconds=window_seconds)
    data['query_history'].update(fetched_at=172800, stale=False)
    data['fetched_at'] = 172800
    path = tmp_path/'prior.json'
    path.write_text(json.dumps(dict(version=1, started_at=time.time(), data=data)))
    restored = pihole.Snapshot(storage_path=str(path))
    assert restored.data is not None
    assert restored.data['upstreams_available'] is True
    assert restored.data['upstreams_partial'] is True
    assert restored.data['partial'] is False
    assert restored.data['configured_upstreams'] == ['1.1.1.1']
    assert restored.data['query_history']['window_seconds'] == 86400
    assert restored.data['query_history']['bins'] == data['query_history']['bins']


def test_full_day_snapshot_roundtrip_is_bounded(tmp_path):
    path = tmp_path/'pihole.json'
    def load():
        return pihole.collect(lambda name: dict(total_queries=20, blocked_queries=3, gravity_entries=100,
            configured_upstreams=[], history=[dict(r, total=10**250+r['total']) for r in full_day()]), now=172800)
    cache = pihole.Snapshot(load, storage_path=str(path))
    cache.current()
    cache.worker.join(2)
    assert path.exists()
    assert 262144 < path.stat().st_size <= 1048576
    restored = pihole.Snapshot(load, storage_path=str(path))
    assert restored.data['query_history'] == cache.data['query_history']
    assert len(restored.data['query_history']['bins']) == 144
    path.write_bytes(b' ' * 1048577)
    assert pihole.Snapshot(load, storage_path=str(path)).data is None

