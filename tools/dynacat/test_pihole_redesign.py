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
 assert p.locator('.nw-dns-plot h4').all_text_contents()==['REQUESTS','BLOCKS']
 h=d['query_history']
 for key in ('total','blocked'):
  plot=p.locator(f'.nw-dns-plot.nw-{key}')
  chart=plot.locator('svg')
  assert chart.get_attribute('viewBox')=='0 0 600 140'
  assert plot.locator('.nw-query-line').get_attribute('d')==h[key]['path']
  assert plot.locator('.nw-query-area').get_attribute('d')==h[key]['area_path']
  assert f"0–{h[key]['max_count']} queries / 10 min" in plot.inner_text()
  assert 160<=chart.bounding_box()['height']<=180
  assert .5<=chart.bounding_box()['width']/p.locator('.nw-dns-body').bounding_box()['width']<=.7
 assert p.locator('.nw-query-area').count()==2
 assert p.locator('.nw-dns-stats').evaluate('e=>getComputedStyle(e).display')=='grid'
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
