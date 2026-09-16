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
 assert p.locator('.nw-query-bin').count()==len(d['query_history']['points'])
 for bin,point in zip(p.locator('.nw-query-bin').all(),d['query_history']['points']):
  assert bin.get_attribute('data-timestamp')==str(point['timestamp'])
  assert bin.get_attribute('data-permitted')==str(point['permitted'])
  assert bin.get_attribute('data-blocked')==str(point['blocked'])
 assert p.locator('.nw-dns-stats').evaluate('e=>getComputedStyle(e).display')=='grid'
 assert p.locator('.nw-query-legend').evaluate('e=>getComputedStyle(e).display')=='flex'
 assert p.bounding_box()['height']<420
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
