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
 chart=p.locator('svg.pve-netgraph')
 assert chart.count()==1
 assert chart.get_attribute('viewBox')=='0 0 100 30'
 assert p.locator('.nw-query-bin,.nw-query-bars').count()==0
 h=d['query_history']
 for key in ('permitted','blocked'):
  assert chart.locator(f'.nw-{key}.nw-query-line').get_attribute('d')==h[key]['path']
 assert p.locator('.pve-netaxis').inner_text().split()==['30m','ago',f"0–{h['max_count']}",'queries','/','10','min','latest']
 assert chart.bounding_box()['height']==38
 assert p.locator('.nw-query-area').count()==0
 for cls,key in (('pve-rx-label','permitted'),('pve-tx-label','blocked')):
  assert p.locator('.'+cls+' b').inner_text()==str(h['points'][-1][key])
 assert p.locator('.nw-dns-stats').evaluate('e=>getComputedStyle(e).display')=='grid'
 assert p.locator('.pve-netaxis').evaluate('e=>getComputedStyle(e).display')=='flex'
 assert p.bounding_box()['height']<420
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
