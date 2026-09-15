import asyncio,json,sys,subprocess,yaml
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 base=sys.argv[1].rstrip('/');out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
 old=yaml.safe_load(subprocess.check_output(['git','show','3f0581dd:tools/dynacat/config/dynacat.yml']))
 expected=[l['url'] for p in old['pages'] if p['name'] in ['Directory','News'] for c in p['columns'] for w in c['widgets'] if w['type']=='bookmarks' for g in w['groups'] for l in g['links']]
 async with async_playwright() as p:
  b=await p.chromium.launch();page=await b.new_page(viewport={'width':1600,'height':1100},timezone_id='Pacific/Kiritimati');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(base+'/endpoints-services');await page.wait_for_selector('.es-endpoint')
  actual=await page.locator('.es-endpoint').evaluate_all('(a)=>a.map(x=>x.getAttribute("href"))');assert sorted(actual)==sorted(expected),(len(actual),len(expected))
  assert await page.locator('.es-group').count()==8
  await page.locator('#endpoint-search').fill('Plex');assert await page.locator('.es-endpoint:visible').count()>0
  await page.locator('#endpoint-search').fill('zzzznoexistingendpoint');assert await page.locator('.es-endpoint:visible').count()==0;assert await page.locator('.es-empty').is_visible()
  await page.locator('#endpoint-search').fill('');await page.locator('[data-es-category="2"]').click();assert await page.locator('.es-group:visible').count()==1
  await page.locator('[data-es-category="all"]').click();assert await page.locator('.es-endpoint:visible').count()==86
  for width in [1600,390]:
   await page.set_viewport_size({'width':width,'height':1100 if width>500 else 844});assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');await page.screenshot(path=str(out/f'endpoints-{width}.png'),full_page=True)
  await page.set_viewport_size({'width':1600,'height':1100})
  aliases={'/directory':'/endpoints-services','/news':'/endpoints-services','/media-ops':'/media','/command-center':'/'}
  for oldpath,newpath in aliases.items():
   await page.goto(base+oldpath);await page.wait_for_url(base+newpath)
  await page.goto(base+'/');await page.wait_for_selector('[data-bern-calendar] [aria-current=date]')
  highlighted=await page.locator('[data-bern-calendar] [aria-current=date]').get_attribute('data-date')
  bern=await page.evaluate("new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich'}).format(new Date())")
  assert highlighted==bern,(highlighted,bern)
  assert await page.locator('.bern-calendar-weekdays').inner_text()=='Mo\nTu\nWe\nTh\nFr\nSa\nSu'
  title=await page.locator('[data-calendar-title]').inner_text();await page.locator('[data-calendar-action=next]').click();assert await page.locator('[data-calendar-title]').inner_text()!=title;await page.locator('[data-calendar-action=today]').click();assert await page.locator('[data-calendar-title]').inner_text()==title
  assert not await page.locator('.cc-rail-clock [data-local-time]').is_visible()
  timezone_rows=await page.locator('.cc-rail-clock [data-time-in-zone]').evaluate_all("rows=>rows.map(r=>({zone:r.dataset.timeInZone,time:r.querySelector('[data-time]').textContent.trim(),expected:new Intl.DateTimeFormat('en-GB',{timeZone:r.dataset.timeInZone,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()),offset:r.querySelector('.cc-clock-zone')?.textContent}))")
  assert [r['zone'] for r in timezone_rows]==['Europe/Zurich','Europe/London','America/Los_Angeles','America/New_York'],timezone_rows
  assert all(r['time']==r['expected'] and r['offset'] for r in timezone_rows),timezone_rows
  clocks=await page.locator('.cc-rail-clock').inner_text();positions=[clocks.index(x) for x in ['Bern','London','San Francisco','New York']];assert positions==sorted(positions),clocks
  labels=await page.locator('.header-container .nav a').all_text_contents();assert not any(x.strip() in ['Directory','News','Media Ops','Command Center'] for x in labels),labels
  await page.screenshot(path=str(out/'clocks-calendar.png'),full_page=True)
  assert not errors,errors
  result=dict(endpoint_count=len(actual),categories=8,links_preserved=True,search=True,aliases=aliases,bern_calendar_date=highlighted,browser_timezone='Pacific/Kiritimati',clock_text=clocks,errors=errors)
  (out/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));await b.close()
asyncio.run(main())
