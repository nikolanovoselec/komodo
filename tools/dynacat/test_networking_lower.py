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
    assert a['y']>=b['y']+b['height']
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

def test_null_history_has_no_fabricated_connection(page):
    # Explicit synthetic gap/zero cases through the real projection and native refresh.
    import sys
    sys.path.insert(0,str(ROOT/'adapter'))
    from pihole import query_history
    path=OUT/'source/network-current'; original=path.read_text(); data=json.loads(original)
    rows=[{'history':[{'timestamp':t,'total':10,'blocked':2} for t in (600,1200,1800)]} for _ in range(2)]
    rows[1]['history'].pop(1)
    h=query_history(rows,1800); data['pihole']['query_history']=h
    try:
        path.write_text(json.dumps(data))
        line=page.locator('.nw-total .nw-query-line')
        expect(line).to_have_attribute('d',h['total']['path'],timeout=12000)
        assert line.get_attribute('d').count('M')==2
        assert page.locator('.nw-query-area').count()==2
        assert page.locator('.nw-total .nw-query-area').get_attribute('d')==h['total']['area_path']
        assert 'Incomplete history' in page.locator('.nw-pihole').inner_text()
        for row in rows:
            row['history']=[{'timestamp':t,'total':0,'blocked':0} for t in (600,1200,1800)]
        h=query_history(rows,1800); data['pihole']['query_history']=h
        path.write_text(json.dumps(data))
        expect(line).to_have_attribute('d',h['total']['path'],timeout=12000)
        assert line.evaluate('e=>e.getBBox().height')==0
    finally:path.write_text(original)


def test_missing_history_is_unavailable_not_zero(page):
    path=OUT/'source/network-current'; original=path.read_text(); data=json.loads(original)
    data['pihole'].pop('query_history',None)
    data['pihole'].update(partial=True,error='',available=True,total_queries=123,blocked_queries=45,gravity_entries=678)
    try:
        path.write_text(json.dumps(data))
        expect(page.locator('.nw-dns-stat b').first).to_have_text('123',timeout=12000)
        expect(page.locator('.nw-query-unavailable')).to_contain_text('Query history unavailable.')
        assert page.locator('.nw-query-bin').count()==0
        assert 'Partial totals · available instances only.' in page.locator('.nw-pihole').inner_text()
    finally:path.write_text(original)
