import pihole
import pytest


@pytest.mark.parametrize('second', [
    {'timestamp': 2100, 'total': 10, 'blocked': 2},
    {'timestamp': 2100, 'total': None, 'blocked': 2},
    {'timestamp': 2100, 'total': -1, 'blocked': 2},
    {'timestamp': 2100, 'total': '10', 'blocked': 2},
    {'timestamp': 2100, 'total': True, 'blocked': 0},
    {'timestamp': 2100, 'total': 10, 'blocked': 11},
    {'timestamp': 2100, 'total': 10, 'blocked': None},
    {'total': 10, 'blocked': 2},
    {'timestamp': 2101, 'total': 10, 'blocked': 2},
    None,
])
def test_total_is_exact_aligned_source_sum_or_null(second):
    first = {'history': [dict(timestamp=2100, total=20, blocked=3)]}
    rows = [first, {'history': [second] if second is not None else []}]
    h = pihole.query_history(rows, 3000)
    point = h['points'][0]
    valid = second == {'timestamp': 2100, 'total': 10, 'blocked': 2}
    assert point['total'] == (30 if valid else None)
    assert point['permitted'] == (25 if valid else None)
    assert point['available_instances'] == (2 if valid else 1)
    assert all(p['total'] is None for p in h['points'][1:])


@pytest.mark.parametrize('middle', ['valid', 'null', 'missing', 'zero'])
def test_total_series_paths_respect_gaps_and_thirty_minute_bounds(middle):
    records = [dict(timestamp=t, total=20, blocked=3)
               for t in (1199, 1200, 1800, 2400, 3000, 3001)]
    if middle == 'null':
        records[2]['total'] = None
    elif middle == 'missing':
        records.pop(2)
    elif middle == 'zero':
        for record in records:
            record.update(total=0, blocked=0)
    h = pihole.query_history([{'history': records}, {'history': records}], 3000)
    total = h['total']
    assert total['max_count'] == (0 if middle == 'zero' else 40)
    assert all(1200 <= p['timestamp'] <= 3000 for p in h['points'])
    assert h['window_seconds'] == 1800 and h['interval_seconds'] == 600
    segments = 2 if middle in ('null', 'missing') else 1
    assert total['path'].count('M') == segments
    assert total['area_path'].count('Z') == segments
    assert total['path'].startswith('M0.00,')
    assert '600.00,' in total['path']
    if middle == 'valid':
        assert total['path'] == 'M0.00,0.00 L200.00,0.00 L400.00,0.00 L600.00,0.00'
    if middle == 'zero':
        assert total['path'] == 'M0.00,140.00 L200.00,140.00 L400.00,140.00 L600.00,140.00'
    if middle == 'null':
        assert h['points'][1]['total'] is None
    if middle == 'missing':
        assert [p['timestamp'] for p in h['points']] == [1200, 2400, 3000]


def test_blocked_uses_independent_scale_and_permitted_retains_legacy_scale():
    first = dict(history=[dict(timestamp=1800, total=20, blocked=3),
                          dict(timestamp=2400, total=10, blocked=1)])
    second = dict(history=[dict(timestamp=1800, total=10, blocked=2),
                           dict(timestamp=2400, total=5, blocked=1)])
    h = pihole.query_history([first, second], 3000)
    assert h['blocked']['max_count'] == 5
    assert h['total']['max_count'] == 30
    assert h['max_count'] == h['permitted']['max_count'] == 25
    assert h['blocked']['path'] == 'M200.00,0.00 L400.00,84.00'
    assert h['total']['path'] == 'M200.00,0.00 L400.00,70.00'
    assert h['permitted']['path'] == 'M200.00,0.00 L400.00,67.20'
    assert h['blocked']['area_path'] == 'M200.00,0.00 L400.00,84.00 L400.00,140 L200.00,140 Z'


def test_aligned_history_exact_sums_and_privacy():
    def fetch(name):
        slave = name == pihole.NAMES[1]
        return dict(total_queries=20, blocked_queries=3, gravity_entries=100,
                    history=[dict(timestamp=t,total=10 if slave else 20,blocked=2 if slave else 3,domain='PRIVATE') for t in (1500,2100,2700)])
    r=pihole.collect(fetch, now=3000)
    h=r['query_history']
    assert h['interval_seconds']==600
    assert [(p['timestamp'],p['permitted'],p['blocked']) for p in h['points']]==[(1500,25,5),(2100,25,5),(2700,25,5)]
    assert h['max_count']==25
    assert h['available'] and not h['partial']
    assert 'recent_permitted' not in r and 'recent_blocked' not in r and 'PRIVATE' not in str(r)
    assert h['permitted']['area_path'] and h['blocked']['path']


def test_missing_and_invalid_bins_are_null_not_zero_and_do_not_bridge():
    def fetch(name):
        rows=[dict(timestamp=t,total=20,blocked=3) for t in (1500,2100,2700)]
        if name==pihole.NAMES[1]: rows[1]['total']=None
        return dict(total_queries=20,blocked_queries=3,gravity_entries=100,history=rows)
    h=pihole.collect(fetch,now=3000)['query_history']
    assert h['partial'] and h['points'][1]['permitted'] is None
    assert h['permitted']['path'].count('M')==2
    assert h['permitted']['area_path'].count('Z')==2
    def missing(name):
        if name==pihole.NAMES[1]: raise TimeoutError()
        return fetch(name)
    h=pihole.collect(missing,now=3000)['query_history']
    assert not h['available'] and h['partial']
    assert all(p['blocked'] is None for p in h['points'])


def test_official_history_only_no_dns_query_export(monkeypatch):
    monkeypatch.setenv('PIHOLE_API_KEY','SECRET')
    calls=[]
    def transport(url,pin,method,path,**kw):
        calls.append(path)
        if method=='POST': return {'session':{'sid':'SID','valid':True}}
        if method=='DELETE': return
        if path=='/api/stats/summary': return {'queries':{'total':20,'blocked':3},'gravity':{'domains_being_blocked':100}}
        if path=='/api/config/dns/upstreams': return {'config': {'dns': {'upstreams': []}}}
        assert path=='/api/history'
        return {'history':[{'timestamp':1500,'total':20,'blocked':3}]}
    row=pihole.fetch_instance(pihole.NAMES[0],transport)
    assert row['history']==[{'timestamp':1500,'total':20,'blocked':3}]
    assert not any('/api/queries' in c for c in calls)


def test_time_labels_and_absent_bin_gap():
    row=dict(history=[dict(timestamp=t,total=20,blocked=3) for t in (1500,2700)])
    h=pihole.query_history([row,row],3000)
    assert h['partial']
    assert h['start']=='00:20'
    assert h['end']=='00:50'
    assert h['permitted']['path'].count('M')==2
