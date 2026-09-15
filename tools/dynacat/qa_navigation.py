import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 url,prefix=sys.argv[1:3]
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
  report={}
  for mode,width,height in [('desktop',1600,1100),('mobile',390,844)]:
   page=await browser.new_page(viewport={'width':width,'height':height},timezone_id='Europe/Zurich',is_mobile=mode=='mobile')
   errors=[]; requests=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.on('request',lambda r:requests.append(r.url) if '/api/' in r.url else None)
   await page.goto(url,wait_until='networkidle',timeout=60000)
   await page.wait_for_selector('.pve-node',timeout=60000)
   await page.locator('.pve-stopped summary').click()
   assert await page.locator('.pve-stopped').get_attribute('open') is not None
   await page.wait_for_timeout(6500)
   assert await page.locator('.pve-stopped').get_attribute('open') is not None, 'Refresh closed the disclosure'
   links=await page.locator('.cc-resource-link,.top-consumers .k-rank-link,.cc-container-link').evaluate_all('(aa)=>aa.map(a=>({name:a.innerText.split("\\n")[0],href:a.href,target:a.target,rel:a.rel}))')
   problems=await page.locator('.cc-container-link').count()
   assert len(links)==37+problems, len(links)
   assert all(x['target']=='_blank' and 'noopener' in x['rel'] for x in links)
   assert sum('proxmox.graymatter.ch/#v1:' in x['href'] for x in links)==27
   assert sum('/container/' in x['href'] for x in links)==10+problems
   assert await page.locator('.pve-node').count()==3
   assert await page.locator('.pve-guests .cc-resource-link').count()==19
   assert await page.locator('.widget-type-bookmarks,.widget-type-releases').count()==0
   assert await page.locator('.cc-rail-clock,.cc-rail-weather').count()==2
   box=await page.locator('.page-column:has(.cc-rail-clock)').bounding_box()
   resource=await page.locator('.pve-resources').bounding_box()
   if mode=='desktop':
    assert box['x'] > resource['x']+resource['width']
    assert abs(box['y']-resource['y'])<1
    assert box['width']==286
   assert await page.locator('.cc-rail-clock').evaluate('e=>e.parentElement===document.querySelector(".renovate-prs").parentElement')
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   await page.locator('.pve-stopped summary').click()
   await page.evaluate('window.scrollTo(0,0)')
   await page.screenshot(path=prefix+'-'+mode+'.png',full_page=True)
   await page.screenshot(path=prefix+'-'+mode+'-viewport.png')
   await page.keyboard.press('Tab')
   await page.locator('.pve-node').first.focus()
   focus=await page.locator('.pve-node').first.evaluate('a=>getComputedStyle(a).outlineStyle')
   assert focus!='none',focus
   focused_href=await page.locator('.pve-node').first.get_attribute('href')
   await page.wait_for_timeout(6500)
   assert await page.evaluate('document.activeElement.getAttribute("href")')==focused_href, 'Refresh lost keyboard focus'
   samples=[]
   if mode=='desktop':
    for _ in range(5):
     samples.append(await page.locator('.pve-resources').evaluate('e=>({at:Date.now(),fetched:e.querySelector(".pve-timestamp").dataset.dynamicRelativeTime,cpu:[...e.querySelectorAll(".pve-cpu meter")].map(m=>m.value)})'))
     await page.wait_for_timeout(5500)
    assert len({s['fetched'] for s in samples})>1,samples
    assert len({str(s['cpu']) for s in samples})>1,samples
   report[mode]={'links':links,'errors':errors,'header_bottom':box['y']+box['height'],'resources_top':resource['y'],'focus':focus,'samples':samples,'requests':requests}
   assert not errors,errors
   await page.close()
  await browser.close()
 Path(prefix+'-verification.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:{'links':len(v['links']),'errors':v['errors'],'samples':v['samples'],'requests':len(v['requests'])} for k,v in report.items()},indent=2))
asyncio.run(main())
