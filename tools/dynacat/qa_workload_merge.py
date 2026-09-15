import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 url=sys.argv[1];out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
 async with async_playwright() as p:
  b=await p.chromium.launch();page=await b.new_page(viewport={'width':1600,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(url);await page.wait_for_selector('.cw-workload');await page.wait_for_timeout(2500)
  assert await page.locator('.pve-node').count()==3
  assert await page.get_by_text('Docker Hosts',exact=True).count()==0
  summaries=await page.locator('.cw-workload').evaluate_all('(rows)=>rows.map(r=>({name:r.querySelector("header strong").textContent,text:r.querySelector(".cw-docker summary").innerText,height:r.getBoundingClientRect().height}))')
  mapped=page.locator('.cw-workload').filter(has=page.locator('.cw-docker-count')).first
  await mapped.locator('summary').click();await page.wait_for_timeout(1500)
  assert await mapped.locator('.cw-container').count()>0
  anchor=mapped.locator('.cw-container').first;await anchor.focus();href=await anchor.get_attribute('href');await page.wait_for_timeout(1600)
  assert await page.evaluate('document.activeElement.getAttribute("href")')==href
  assert await mapped.locator('details').get_attribute('open') is not None
  await page.screenshot(path=str(out/'expanded.png'),full_page=True)
  await mapped.locator('summary').click()
  for theme in ['catppuccin-latte','midnight-navy']:
   await page.locator('.header-container .theme-picker').hover();await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click();await page.wait_for_timeout(300);await page.reload();await page.wait_for_selector('.cw-workload')
   for width in [1600,1024,390]:
    await page.set_viewport_size({'width':width,'height':1100 if width>500 else 844});await page.evaluate('scrollTo(0,0)');await page.wait_for_timeout(150)
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
    await page.screenshot(path=str(out/f'{width}-{theme}.png'),full_page=True)
   await page.set_viewport_size({'width':1600,'height':1100})
  assert not errors,errors
  report={'guests':summaries,'errors':errors,'focus_preserved':True,'disclosure_preserved':True,'physical_nodes':3,'separate_docker_hosts':False}
  (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));await b.close()
asyncio.run(main())
