"""Additional synthetic coverage/availability regression cases."""
import copy
import json
import time
import pytest
import pihole
from test_pihole_24h import full_day


@pytest.mark.parametrize('fault', ['missing', 'invalid', 'absent', 'zero', 'short'])
def test_daily_coverage_never_stretches_or_bridges(fault):
    rows = [{'history': full_day()} for _ in range(2)]
    if fault == 'missing': rows[1]['history'].pop(70)
    if fault == 'invalid': rows[1]['history'][70]['total'] = None
    if fault == 'absent': rows.pop()
    if fault == 'short':
        for row in rows: row['history'] = row['history'][-3:]
    if fault == 'zero':
        for row in rows:
            for record in row['history']: record.update(total=0, blocked=0)
    h = pihole.query_history(rows,172800)
    assert h['window_seconds'] == 86400 and h['end_epoch']-h['start_epoch'] == 86400
    assert h['partial'] is (fault != 'zero')
    if fault in ('missing','invalid'):
        assert h['total']['curve_path'].count('M') == 2
        assert h['total']['curve_area_path'].count(' Z') == 2
        assert sum(s['width'] for s in h['missing_spans']) == pytest.approx(600/144)
    if fault == 'absent':
        assert not h['available'] and not h['total']['curve_path']
    if fault == 'zero':
        assert h['total']['curve_path'].startswith('M0.000000,140.000000')
        assert h['total']['curve_path'].endswith('600.000000,140.000000')
    if fault == 'short':
        assert h['total']['curve_path'].startswith('M587.500000,')
        assert h['coverage_start_epoch'] == 171000


def test_upstream_partial_and_empty_are_distinct_from_unavailable():
    def fetch(name):
        if name == pihole.NAMES[1]: raise TimeoutError()
        return dict(total_queries=20, blocked_queries=3, gravity_entries=100,
                    configured_upstreams=['1.1.1.1'], upstreams_truncated=True, history=[])
    result = pihole.collect(fetch, now=172800)
    assert result['partial'] and result['gravity_entries'] == 100
    assert result['configured_upstreams'] == ['1.1.1.1']
    assert result['upstreams_available'] and result['upstreams_truncated']
    assert pihole.aggregate_upstreams([dict(configured_upstreams=[], upstreams_available=True)]) == dict(configured_upstreams=[], upstreams_available=True, upstreams_partial=False, upstreams_truncated=False)
    assert pihole.unavailable()['upstreams_available'] is False


def test_malformed_instance_snapshot_is_rejected(tmp_path):
    data = pihole.collect(lambda name: dict(total_queries=20, blocked_queries=3, gravity_entries=100, history=[]), now=172800)
    data.update(fetched_at=172800, instances=[None, None])
    data['query_history'].update(fetched_at=172800, stale=False)
    path = tmp_path/'bad.json'
    path.write_text(json.dumps(dict(version=1, started_at=time.time(), data=data)))
    assert pihole.Snapshot(storage_path=str(path)).data is None
