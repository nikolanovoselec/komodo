import json
from playwright.sync_api import expect
from test_networking_lower import page,SOURCE,OUT

def test_pihole_first_compact_operational_panel(page):
 p=page.locator('.nw-pihole');i=page.locator('.nw-infrastructure')
 assert p.bounding_box()['y']<i.bounding_box()['y']
 d=json.loads(SOURCE.read_text())['pihole']
 assert p.locator('.nw-dns-stat b').all_text_contents()[:2]==[str(d['total_queries']),str(d['blocked_queries'])]
 assert 'Blocked rate' in p.inner_text()
 assert 'Blocklist entries' in p.inner_text() and 'not deduplicated' in p.inner_text()
 for inst in d['instances']:
  row=p.locator('.nw-resolver').filter(has_text=inst['name'])
  for upstream in inst['configured_upstreams']: assert upstream in row.inner_text()
 chart=p.locator('svg.nw-query-timeline')
 assert chart.count()==1
 assert chart.get_attribute('viewBox')=='0 0 600 140'
 assert p.locator('.nw-query-bin,.nw-query-bars').count()==0
 h=d['query_history']
 for key in ('permitted','blocked'):
  assert chart.locator(f'.nw-{key}.nw-query-line').get_attribute('d')==h[key]['path']
  assert chart.locator(f'.nw-{key}.nw-query-area').get_attribute('d')==h[key]['area_path']
 assert p.locator('.nw-query-scale').inner_text().split()==[str(h['max_count']),'0']
 assert p.locator('.nw-query-time').inner_text().split()==[h['start'],h['end']]
 assert chart.bounding_box()['width']>p.bounding_box()['width']*.8
 assert p.locator('.nw-dns-stat b').first.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')<=24
 for key in ('permitted','blocked'):
  assert float(chart.locator(f'.nw-{key}.nw-query-area').evaluate('e=>getComputedStyle(e).fillOpacity'))>=.35
 assert p.locator('.nw-dns-stats').evaluate('e=>getComputedStyle(e).display')=='grid'
 assert p.locator('.nw-query-legend').evaluate('e=>getComputedStyle(e).display')=='flex'
 assert p.bounding_box()['height']<420
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
