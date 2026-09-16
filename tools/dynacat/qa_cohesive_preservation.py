"""Additional captured-native preservation checks (no live changes)."""
import json,re,hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'cohesive-qa'
data=json.loads((OUT/'source/network-current').read_text());history=data['pihole']['query_history']
# Independently check actual source ordinates against official count bins. Two decimals in provider paths.
for key in ('total','blocked'):
    coordinates=re.findall(r'[ML]([\d.]+),([\d.]+)',history[key]['path'])
    pts=[p for p in history['points'] if p.get(key) is not None and p.get('available_instances')==2]
    assert len(coordinates)==len(pts)
    for (x,y),point in zip(coordinates,pts):assert abs(float(y)-(140-140*point[key]/history[key]['max_count']))<=.011
    for a,b in zip(coordinates,coordinates[1:]):assert abs(float(b[0])-float(a[0])-200)<.02
with sync_playwright() as p:
    browser=p.chromium.launch()
    for width in (1600,390):
        context=browser.new_context(viewport={'width':width,'height':1100},is_mobile=width==390,has_touch=width==390)
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith('http://172.19.0.4:8080/') and r.request.resource_type!='media' else r.abort())
        page=context.new_page();page.goto('http://172.19.0.4:8080/networking');page.locator('.nw-pihole').wait_for()
        text=page.locator('.nw-pihole').inner_text()
        for key in ('total_queries','blocked_queries','gravity_entries'):assert str(data['pihole'][key]) in text
        assert 'includes blocks' in text and 'not deduplicated' in text and 'Configured forwarders' in text
        for instance in data['pihole']['instances']:
            assert instance['name'] in text
            for ip in instance['configured_upstreams']:assert ip in text
        a=page.locator('.nw-pihole').bounding_box();g=page.locator('.nw-gateway').bounding_box();infra=page.locator('.nw-infrastructure').bounding_box()
        assert infra['y']>=g['y']+g['height']
        if width==390:assert g['y']>=a['y']+a['height'] and abs(g['width']-a['width'])<1
        assert page.locator('.nw-group>h3').all_text_contents()==['Switches','Access points','Internet backup']
        page.goto('http://172.19.0.4:8080/hardware-workloads');page.locator('.cw-workloads').wait_for()
        assert page.locator('.cw-workload>.k-host').evaluate_all('es=>es.every(e=>e.getBoundingClientRect().height>=44 && e.href && e.title)')
        assert page.locator('.cw-history-chart').evaluate_all('es=>es.every(e=>e.title && e.querySelector("svg[aria-label]"))')
        context.close()
    browser.close()
print('Captured official bins → coordinates, retained totals/forwarders/grouping, stacking, links/tooltips: PASS')
