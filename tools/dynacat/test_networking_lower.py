"""Native renderer lower-page acceptance. Source capture is real; Pi-hole fixtures are synthetic."""
import copy
import json
import shutil
import subprocess
import time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
import qa_networking_layout as qa

ROOT = Path(__file__).parent
OUT = ROOT.parents[1] / 'networking-lower-qa'

@pytest.fixture(scope='module')
def page():
    OUT.mkdir(exist_ok=True)
    (OUT/'source').mkdir(exist_ok=True)
    source = json.loads((ROOT.parents[1]/'networking-layout-qa/source/network-current').read_text())
    source['pihole'] = {'available':False,'error':'Pi-hole integration unavailable: collector cannot reach either instance.','instances':[{'name':n,'available':False} for n in ('pihole-master.lan','pihole-slave.lan')], 'total_queries':None,'blocked_queries':None,'gravity_entries':None,'recent_permitted':[],'recent_blocked':[]}
    (OUT/'source/network-current').write_text(json.dumps(source))
    qa.OUT = OUT
    qa.NAMES = ('networking-lower-renderer','networking-layout-source')
    qa.prepare('candidate',18146)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1600,'height':1100})
            for attempt in range(30):
                try:
                    page.goto('http://127.0.0.1:18146/networking')
                    page.locator('.nw-dashboard').wait_for(timeout=1500)
                    break
                except Exception:
                    if attempt == 29: raise
                    time.sleep(.2)
            yield page
            browser.close()
    finally:
        qa.cleanup()

def test_overview_summary_and_wan_removed_without_losing_gateway(page):
    assert page.locator('.nw-heading, .nw-summary, .nw-wan').count() == 0
    assert 'NETWORK OVERVIEW' not in page.locator('.nw-dashboard').inner_text()
    assert page.locator('.nw-gateway').count() > 0
    assert page.locator('.nw-infrastructure .nw-area').count() > 0
    assert page.locator('.nw-connected [data-nw-client]').count() > 0


def test_network_css_cache_version_matches_content():
    import hashlib
    import re
    config=(ROOT/'config/dynacat.yml').read_text()
    actual=hashlib.sha256((ROOT/'assets/networking.css').read_bytes()).hexdigest()[:12]
    assert re.search(r'/assets/networking.css\?v=([a-f0-9]+)',config).group(1)==actual

def test_missing_pihole_source_explains_blocker(page):
    from playwright.sync_api import expect
    path=OUT/'source/network-current'
    original=path.read_text()
    data=json.loads(original)
    del data['pihole']
    try:
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-pihole .nw-warning')).to_contain_text('network access and protected API authentication',timeout=12000)
        for name in ('pihole-master.lan','pihole-slave.lan'):
            assert name in page.locator('.nw-pihole').inner_text()
    finally:
        path.write_text(original)
        expect(page.locator('.nw-pihole .nw-warning')).to_contain_text('collector cannot reach',timeout=12000)

def test_pihole_unavailable_is_not_zero(page):
    panel=page.locator('.nw-pihole')
    assert 'collector cannot reach either instance' in panel.inner_text()
    assert panel.locator('.nw-dns-stat b').all_text_contents()==['Unavailable']*3
    assert 'Gravity entries · sum' in panel.inner_text()
    for name in ('pihole-master.lan','pihole-slave.lan'):
        assert name in panel.inner_text()
    assert panel.get_by_role('heading',name='Permitted DNS queries').count()==1
    assert panel.get_by_role('heading',name='Blocked DNS queries').count()==1
    assert panel.locator('.nw-dns-history .nw-empty').all_text_contents()==['Query history unavailable.']*2

def test_available_query_history_is_bounded_and_status_is_explicit(page):
    from playwright.sync_api import expect
    path=OUT/'source/network-current'
    original=path.read_text()
    data=json.loads(original)
    data['pihole'].update(available=True,partial=False,error='',total_queries=0,blocked_queries=12,gravity_entries=2468)
    for instance in data['pihole']['instances']:
        instance['available']=True
    for kind in ('permitted','blocked'):
        data['pihole']['recent_'+kind]=[{'domain':f'{kind}-{i}.example','time':'2026-09-16T12:00:00Z','status':'FORWARDED' if kind=='permitted' else 'GRAVITY','instance':'pihole-master.lan'} for i in range(12)]
    try:
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-dns-stat b').first).to_have_text('0',timeout=12000)
        for kind in ('permitted','blocked'):
            rows=page.locator('[data-dns-kind="'+kind+'"] .nw-dns-query')
            assert rows.count()==10
            assert f'{kind}-0.example' in rows.first.inner_text()
            assert 'Response status:' in rows.first.inner_text()
            assert 'pihole-master.lan' in rows.first.inner_text()
        assert page.locator('.nw-dns-stat b').all_text_contents()==['0','12','2468']
        panel=page.locator('.nw-pihole')
        assert panel.locator('.nw-warning').count()==0
        assert 'Across both instances.' in panel.inner_text()
        assert 'Gravity entries are summed, not deduplicated.' in panel.inner_text()
        assert panel.get_by_role('heading',name='Permitted DNS queries',exact=True).count()==1
        assert 'resolved' not in panel.inner_text().casefold()
        assert 'FORWARDED' in panel.locator('[data-dns-kind="permitted"]').inner_text()
    finally:
        path.write_text(original)
        expect(page.locator('.nw-dns-stat b').first).to_have_text('Unavailable',timeout=12000)

@pytest.mark.parametrize('error', ['pihole-slave.lan: API authentication unavailable', ''])
def test_partial_pihole_warns_even_when_available(page, error):
    from playwright.sync_api import expect
    path=OUT/'source/network-current'
    original=path.read_text()
    data=json.loads(original)
    data['pihole'].update(available=True, partial=True,
        error=error,
        total_queries=123, blocked_queries=45, gravity_entries=678)
    data['pihole']['instances'][0]['available']=True
    try:
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-dns-stat b').first).to_have_text('123',timeout=12000)
        panel=page.locator('.nw-pihole')
        expect(panel.locator('.nw-warning')).to_contain_text(error or 'Partial Pi-hole data · one or more instances are unavailable.')
        assert 'Partial totals · available instances only.' in panel.inner_text()
        assert 'Across both instances.' not in panel.inner_text()
        assert panel.locator('.nw-dns-stat b').all_text_contents()==['123','45','678']
    finally:
        path.write_text(original)
        expect(page.locator('.nw-dns-stat b').first).to_have_text('Unavailable',timeout=12000)


def test_expanded_client_filter_survives_native_refresh(page):
    from playwright.sync_api import expect
    path=OUT/'source/network-current'
    original=path.read_text()
    data=json.loads(original)
    query=data['clients'][0]['ip']
    search=page.locator('[data-nw-search]')
    try:
        search.fill(query)
        search.focus()
        search.evaluate('e=>e.setSelectionRange(2,2)')
        data['pihole']['error']='Native refresh acceptance marker'
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-pihole .nw-warning')).to_have_text('Native refresh acceptance marker',timeout=12000)
        assert search.input_value()==query
        assert search.evaluate('e=>e.selectionStart')==2
        assert page.locator('[data-nw-client]:visible').count()==1
        assert page.locator('.nw-connected details').count()==0
    finally:
        search.fill('')
        path.write_text(original)
        expect(page.locator('.nw-pihole .nw-warning')).to_contain_text('collector cannot reach',timeout=12000)

def test_metric_hierarchy_and_mobile_stack(page):
    stats=page.locator('.nw-dns-stat')
    rects=[stats.nth(i).bounding_box() for i in range(3)]
    assert len({r['y'] for r in rects})==1, 'Metrics must share a compact summary row'
    assert rects[0]['x']<rects[1]['x']<rects[2]['x']
    page.set_viewport_size({'width':390,'height':1100})
    a=page.locator('.nw-connected').bounding_box();b=page.locator('.nw-pihole').bounding_box()
    assert b['y']>=a['y']+a['height']
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.set_viewport_size({'width':1600,'height':1100})

def test_lower_page_is_expanded_clients_left_pihole_right(page):
    lower=page.locator('.nw-lower')
    assert lower.count()==1, 'Missing split lower-page section'
    clients=lower.locator('.nw-connected')
    assert clients.locator('[data-nw-client]:visible').count()>0
    assert clients.locator('details').count()==0
    assert lower.locator('.nw-pihole').count()==1
    for heading in ('Networks & VLANs','WiFi','Firewall rules','Source capabilities'):
        assert page.get_by_role('heading',name=heading,exact=True).count()==0
    assert page.locator('[data-nw-disclosure="firewall"],[data-nw-disclosure="capabilities"]').count()==0
    a=clients.bounding_box(); b=lower.locator('.nw-pihole').bounding_box()
    assert a['x']<b['x'] and abs(a['width']-b['width'])<2
    assert abs(a['y']-b['y'])<2
