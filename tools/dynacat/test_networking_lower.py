"""Native networking acceptance; real inventory plus explicitly synthetic edge-case history."""
import hashlib
import json
import os
import re
import time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect
import qa_networking_layout as qa

ROOT=Path(__file__).parent
OUT=ROOT.parents[1]/'networking-query-qa'
SOURCE=Path(os.environ.get('NETWORK_QA_SOURCE','/tmp/network-query-current.json'))

@pytest.fixture(scope='module')
def page():
    (OUT/'source').mkdir(parents=True,exist_ok=True)
    source=json.loads(SOURCE.read_text())
    source.pop('clients',None)
    for key in ('recent_permitted','recent_blocked'):
        source.get('pihole',{}).pop(key,None)
    (OUT/'source/network-current').write_text(json.dumps(source))
    qa.OUT=OUT
    qa.NAMES=('networking-query-renderer','networking-layout-source')
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
                    if attempt==29: raise
                    time.sleep(.2)
            yield page
            browser.close()
    finally: qa.cleanup()

def test_clients_removed_and_pihole_full_width_below_preserved_infrastructure(page):
    assert page.locator('.nw-connected,[data-nw-client],[data-nw-search]').count()==0
    source=json.loads(SOURCE.read_text())
    assert page.locator('.nw-device').count()==len(source['devices'])
    assert page.locator('.nw-gateway').count()==1
    a=page.locator('.nw-infrastructure').bounding_box()
    b=page.locator('.nw-pihole').bounding_box()
    assert b['y']>=a['y']+a['height']
    assert abs(a['width']-b['width'])<2
    for device in source['devices']:
        card=page.locator('.nw-device').filter(has=page.locator('h4',has_text=re.compile('^'+re.escape(device['name'])+'(?: ↗)?$')))
        for index,key in enumerate(('cpu','ram','rx','tx')):
            h=device['history'][key]
            if h.get('samples',0)>1 and h.get('path'):
                metric=card.locator('.nw-metric').nth(index)
                assert metric.locator('path:not(.nw-area):not(.nw-gridline)').get_attribute('d')==h['path']
                assert metric.locator('.nw-area').get_attribute('d')==h['area_path']
    for heading in ('Networks & VLANs','WiFi','Firewall rules','Source capabilities'):
        assert page.get_by_role('heading',name=heading,exact=True).count()==0

def test_network_css_cache_version_matches_content():
    config=(ROOT/'config/dynacat.yml').read_text()
    actual=hashlib.sha256((ROOT/'assets/networking.css').read_bytes()).hexdigest()[:12]
    assert re.search(r'/assets/networking.css\?v=([a-f0-9]+)',config).group(1)==actual

def test_combined_chart_replaces_lists_and_preserves_gap_paths(page):
    path=OUT/'source/network-current'
    original=path.read_text()
    data=json.loads(original)
    h={'available':True,'partial':True,'interval_seconds':600,'window_seconds':1800,
       'start':'2026-09-16T12:00:00Z','end':'2026-09-16T12:30:00Z','max_count':100,
       'points':[], 'error':'',
       'permitted':{'path':'M0 70 L200 28 M600 42','area_path':'M0 70 L200 28 L200 140 L0 140 Z M600 42 L600 140 L600 140 Z'},
       'blocked':{'path':'M0 126 L200 112 M600 119','area_path':'M0 126 L200 112 L200 140 L0 140 Z M600 119 L600 140 L600 140 Z'}}
    data['pihole']['query_history']=h
    try:
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-query-line[data-series="permitted"]')).to_have_attribute('d',h['permitted']['path'],timeout=12000)
        panel=page.locator('.nw-pihole')
        assert panel.locator('.nw-dns-query,.nw-dns-history').count()==0
        assert page.locator('.nw-query-chart svg').get_attribute('viewBox')=='0 0 600 140'
        for kind in ('permitted','blocked'):
            assert panel.locator('.nw-query-line[data-series="'+kind+'"]').get_attribute('d')==h[kind]['path']
            assert panel.locator('.nw-query-area[data-series="'+kind+'"]').get_attribute('d')==h[kind]['area_path']
        assert 'Queries / 10 min' in panel.inner_text()
        assert 'Last 30 minutes' in panel.inner_text()
        assert 'Permitted (total−blocked; not guaranteed successful resolutions)' in panel.inner_text()
        assert panel.locator('.nw-query-axis time').all_text_contents()==[h['start'],h['end']]
        assert 'UTC' in panel.locator('.nw-query-axis').inner_text()
        assert 'Incomplete history' in panel.inner_text()
        assert panel.locator('.nw-dns-stat b').all_text_contents()==[str(data['pihole'][k]) for k in ('total_queries','blocked_queries','gravity_entries')]
        for theme,key in (('dark','midnight-navy'),('light','catppuccin-latte')):
            page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
            styles=panel.locator('.nw-query-area').evaluate_all('es=>es.map(e=>({fill:getComputedStyle(e).fill,opacity:+getComputedStyle(e).fillOpacity}))')
            assert len({s['fill'] for s in styles})==2
            assert all(s['fill']!='none' and .3<=s['opacity']<1 for s in styles)
    finally:
        path.write_text(original)



def test_missing_history_is_unavailable_not_zero_and_partial_totals_remain(page):
    path=OUT/'source/network-current'; original=path.read_text(); data=json.loads(original)
    data['pihole'].pop('query_history',None)
    data['pihole'].update(partial=True,error='',available=True,total_queries=123,blocked_queries=45,gravity_entries=678)
    try:
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-dns-stat b').first).to_have_text('123',timeout=12000)
        expect(page.locator('.nw-query-unavailable')).to_contain_text('Query history unavailable.')
        assert page.locator('.nw-query-chart svg').count()==0
        assert 'Partial totals · available instances only.' in page.locator('.nw-pihole').inner_text()
        assert page.locator('.nw-dns-stat b').all_text_contents()==['123','45','678']
        data['pihole'].update(available=False,total_queries=None,blocked_queries=None,gravity_entries=None)
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-dns-stat b').first).to_have_text('Unavailable',timeout=12000)
        assert page.locator('.nw-dns-stat b').all_text_contents()==['Unavailable']*3
    finally: path.write_text(original)
