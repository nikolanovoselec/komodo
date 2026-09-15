"""Real Chromium mobile scroll regression, using live widgets and touch input."""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
async def delayed(route,page):
 response=await route.fetch()
 await page.evaluate('scrollTo(0,scrollY+100)')
 await page.wait_for_timeout(40)
 await route.fulfill(response=response)
async def main():
 base=sys.argv[1].rstrip('/'); out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
 staged='--staged' in sys.argv
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True)
  page=await b.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
  if staged:
   async def asset(route):
    name=route.request.url.split('/assets/')[1].split('?')[0];f=ROOT/'assets'/name
    if f.is_file():await route.fulfill(path=str(f))
    else:await route.continue_()
   await page.route('**/assets/*',asset)
  await page.add_init_script('''window.scrollTrace=[];const original=window.scrollBy;window.scrollBy=function(...a){scrollTrace.push({y:scrollY,args:a});return original.apply(this,a)};''')
  await page.goto(base+'/hardware-workloads');await page.wait_for_selector('.cw-docker summary');await page.locator('.cw-docker summary').first.click();await page.wait_for_timeout(1200)
  c=await page.context.new_cdp_session(page)
  await c.send('Network.enable');await c.send('Network.emulateNetworkConditions',{'offline':False,'latency':180,'downloadThroughput':-1,'uploadThroughput':-1})
  # Reproduce the tail of a touch fling: viewport movement after the last input event.
  await page.route('**/api/widgets/*/content/**',lambda route: delayed(route,page))
  for i in range(20):
   if await page.evaluate('scrollY>3500'):await page.evaluate('scrollTo(0,1100)')
   await c.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':180,'y':700}]})
   for y in [600,500,400,300,200]:
    await c.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':180,'y':y}]});await page.wait_for_timeout(35)
   await c.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});await page.wait_for_timeout(500)
  trace=await page.evaluate('scrollTrace');(out/'scroll.json').write_text(json.dumps(trace,indent=2))
  assert not [t for t in trace if t['args'] and isinstance(t['args'][0],dict) and t['args'][0].get('top',0)<-2],trace
  await page.unroute_all(behavior='ignoreErrors');await b.close()
asyncio.run(main())
