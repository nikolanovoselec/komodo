"""Read-only live/captured native screenshot matrix."""
import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path(__file__).resolve().parents[2]/'pihole-redesign-qa'; OUT.mkdir(exist_ok=True)
url=sys.argv[1]; variant=sys.argv[2]
with sync_playwright() as p:
 b=p.chromium.launch(); report=[]
 for width in (1600,390):
  for theme,key in [('dark','midnight-navy'),('light','catppuccin-latte')]:
   c=b.new_context(viewport={'width':width,'height':1100},is_mobile=width==390,has_touch=width==390,color_scheme=theme)
   c.add_init_script("HTMLMediaElement.prototype.play=()=>Promise.reject(new Error('QA no playback'))")
   page=c.new_page();page.goto(url);page.locator('.nw-pihole').wait_for()
   page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()');page.wait_for_timeout(1000)
   panel=page.locator('.nw-pihole'); page.screenshot(path=str(OUT/f'{variant}-{theme}-{width}-page.png'),full_page=True);panel.screenshot(path=str(OUT/f'{variant}-{theme}-{width}-pihole.png'))
   m={'width':width,'theme':theme,'panel':panel.bounding_box(),'infrastructure':page.locator('.nw-infrastructure').bounding_box(),'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth'),'text':panel.inner_text()}
   if width==390:
    page.evaluate('scrollTo(0,0)');s=c.new_cdp_session(page);s.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':195,'y':850}]})
    for y in (750,650,550,450,350):
     s.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':195,'y':y}]});page.wait_for_timeout(30)
    s.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_timeout(1300)
    initial=page.evaluate('scrollY');page.wait_for_timeout(6500);m['touchScroll']=initial;m['refreshDrift']=page.evaluate('scrollY')-initial
    assert initial>0 and abs(m['refreshDrift'])<3
   assert not m['overflow'];report.append(m);c.close()
 b.close();(OUT/f'{variant}-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
