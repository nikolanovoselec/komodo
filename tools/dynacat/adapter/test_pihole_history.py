import pihole


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
