"""Read-only browser acceptance: responsive layout, retained controls and live cadence."""
import asyncio,sys,json,statistics
from playwright.async_api import async_playwright
from pathlib import Path
ROOT=Path(__file__).parent
async def main():
 base=sys.argv[1].rstrip('/');out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);report=[]
 async with async_playwright() as p:
  b=await p.chromium.launch();page=await b.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  if '--staged' in sys.argv:
   async def asset(r):
    f=ROOT/'assets'/r.request.url.split('/assets/')[1].split('?')[0]
    if f.is_file():await r.fulfill(path=str(f))
    else:await r.continue_()
   await page.route('**/assets/*',asset)
  await page.add_init_script('''window.updates={};document.addEventListener('dynacat:widget-updated',e=>{const k=e.detail.widget.dataset.widgetId;(updates[k]??=[]).push(Date.now())});''')
  for width in [390,768,1024,1600]:
   await page.set_viewport_size({'width':width,'height':900});await page.goto(base+'/hardware-workloads');await page.wait_for_selector('.pve-node');await page.wait_for_selector('.cc-rail-weather .weather-columns')
   select=page.locator('select[aria-label="Navigate pages"]')
   assert await select.is_visible()==(width<=767)
   assert await select.locator('option').all_text_contents()==['Hardware & Workloads','Media','Endpoints & Services']
   if width<=767:
    assert not await page.locator('.cc-rail-clock').is_visible()
    assert not await page.locator('[data-bern-calendar]').is_visible()
    w=await page.locator('.cc-rail-weather').bounding_box();h=await page.locator('.pve-resources').bounding_box();assert w['y']+w['height']<=h['y']
    assert not await page.locator('.mobile-navigation').is_visible()
    assert await page.locator('.mobile-navigation-offset').evaluate('e=>e.getBoundingClientRect().height')==0
   else:
    await page.locator('.cc-rail-clock').scroll_into_view_if_needed();await page.wait_for_timeout(200)
    assert await page.locator('.cc-rail-clock').is_visible()
    await page.locator('[data-bern-calendar]').scroll_into_view_if_needed();await page.wait_for_timeout(200)
    assert await page.locator('[data-bern-calendar]').is_visible(),await page.locator('[data-bern-calendar]').evaluate('e=>({html:e.outerHTML,display:getComputedStyle(e).display,rect:e.getBoundingClientRect().toJSON()})')
    if width==1600:
     rail=await page.locator('.page-column:has(.cc-rail-clock)').bounding_box();assert rail['width']==286
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   # Focus and expansion must survive actual native polling; no fake data.
   summary=page.locator('.cw-docker summary').first;await summary.click();await summary.focus();await page.wait_for_timeout(3300)
   assert await page.locator('.cw-docker').first.get_attribute('open') is not None
   assert await page.evaluate('document.activeElement.matches(".cw-docker summary")')
   await page.locator('[data-cw-collapse]').first.click();assert await page.locator('.cw-docker').first.get_attribute('open') is None
   for focused in [False,True]:
    if focused:await page.locator('.pve-node').first.focus()
    else:await page.evaluate('document.activeElement.blur()')
    await page.evaluate('scrollTo(0,0)')
    for _ in range(12):
     y=await page.evaluate('scrollY');await page.mouse.wheel(0,90);await page.wait_for_timeout(220);z=await page.evaluate('scrollY');assert z>=y-2,(width,focused,y,z)
   for theme in ['catppuccin-latte','midnight-navy']:
    await page.evaluate('scrollTo(0,0)');await page.locator('.header .theme-picker').hover();await page.wait_for_timeout(350)
    await page.locator('.theme-choices .theme-preset[data-key="'+theme+'"]:visible').first.click()
    await page.wait_for_function('(t)=>document.documentElement.dataset.theme===t',arg=theme)
    await page.reload();await page.wait_for_selector('.pve-node');await page.wait_for_timeout(5500)
    assert await page.locator('html').get_attribute('data-theme')==theme
    await page.evaluate('scrollTo(0,0)');await page.screenshot(path=str(out/f'hardware-{width}-{theme}.png'))
   u=await page.evaluate('updates');deltas=[b-a for samples in u.values() for a,b in zip(samples,samples[1:])];assert deltas and statistics.median(deltas)<1600,deltas
   report.append({'width':width,'poll_median_ms':statistics.median(deltas),'updates':sum(map(len,u.values()))})
  # Resizing same document must not duplicate navigation or disturb the desktop rail.
  for width in [390,768,390,1600,390]:
   await page.set_viewport_size({'width':width,'height':844});assert await page.locator('.cc-page-select').count()==1
   assert await page.locator('.cc-page-select').is_visible()==(width==390)
  for route,selector in [('media','.mo-poster'),('endpoints-services','.es-launcher'),('hardware-workloads','.pve-node')]:
   await page.locator('.cc-page-select').select_option('/'+route);await page.wait_for_url(base+'/'+route);await page.wait_for_selector(selector)
   assert await page.locator('.cc-page-select').input_value()=='/'+route
   await page.screenshot(path=str(out/f'{route}-390.png'))
   if route=='media':
    await page.locator('.mo-server').first.focus();await page.wait_for_timeout(3200)
    assert await page.evaluate('document.activeElement.matches(".mo-server")')
    for focused in [True,False]:
     if not focused:await page.evaluate('document.activeElement.blur()')
     await page.evaluate('scrollTo(0,0)')
     for _ in range(18):
      y=await page.evaluate('scrollY');await page.mouse.wheel(0,100);await page.wait_for_timeout(230);assert await page.evaluate('scrollY')>=y-2
    await page.evaluate('scrollTo(0,0)');await page.locator('.header .current-theme-preview').tap()
    await page.locator('.theme-choices [data-key="catppuccin-latte"]:visible').first.tap()
    await page.wait_for_function('()=>document.documentElement.dataset.scheme==="light"')
  await page.go_back();await page.wait_for_selector('.es-launcher');assert await page.locator('.cc-page-select').input_value()=='/endpoints-services'
  await page.go_back();await page.wait_for_selector('.mo-poster');assert await page.locator('.cc-page-select').input_value()=='/media'
  assert not errors,errors
  (out/'layout-report.json').write_text(json.dumps({'variants':report,'errors':errors},indent=2));print(json.dumps(report))
  await page.unroute_all(behavior='ignoreErrors');await b.close()
asyncio.run(main())
