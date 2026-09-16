"""Browser regression against real native-rendered, changing live widget payloads.
Run with dynacat-qa-venv python; --candidate routes only candidate JS/gateway transforms.
No metrics are synthesized and audio is blocked.
"""
import json,sys,re
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=Path(__file__).parent
OUT=Path('/srv/hermes/workspaces/mobile-scroll-evidence');OUT.mkdir(exist_ok=True)
URL='http://192.168.2.72:8080'
candidate='--candidate' in sys.argv
engine='webkit' if '--webkit' in sys.argv else 'chromium'
INIT="""window.events=[];window.samples=[];window.updates=0;HTMLMediaElement.prototype.play=()=>Promise.reject(Error('QA no playback'));document.addEventListener('dynacat:widget-updated',e=>{if(e.detail?.widget){updates++;events.push({type:'update',id:e.detail.widget.dataset.widgetId,y:scrollY,h:document.documentElement.scrollHeight})}});function sample(){samples.push(scrollY);requestAnimationFrame(sample)}requestAnimationFrame(sample);"""
results=[]
with sync_playwright() as p:
 b=getattr(p,engine).launch()
 for route in ['hardware-workloads','networking','media']:
  c=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True);c.add_init_script(INIT)
  if candidate:
   def assets(r):
    name=r.request.url.split('/assets/')[1].split('?')[0];f=BASE/'assets'/name
    if f.exists():r.fulfill(path=str(f),content_type='text/javascript' if name.endswith('.js') else 'text/css')
    else:r.continue_()
   c.route('**/assets/*',assets)
   def native(r):
    res=r.fetch();src=res.text()
    # Apply the exact release gateway replacements to the unmodified native module.
    for old,new in re.findall(r"sub_filter '([^']*)' '([^']*)';",(BASE/'gateway.conf').read_text()):
     if old not in ('setupPage().then(() => {','/js/page.js'):src=src.replace(old,new,1)
    r.fulfill(response=res,body=src)
   c.route('**/js/page.js*',native)
  page=c.new_page();page.goto(URL+'/'+route);page.wait_for_timeout(2500)
  ds=page.locator('details');ds.nth(min(1,ds.count()-1)).evaluate('(e)=>{e.open=true;e.querySelector("summary").focus({preventScroll:true})}')
  page.evaluate('scrollTo({top:document.documentElement.scrollHeight-1100,behavior:"instant"})');page.wait_for_timeout(1200)
  page.evaluate('samples=[];events=[];updates=0');page.wait_for_timeout(12000)
  result=page.evaluate('({min:Math.min(...samples),max:Math.max(...samples),updates,events,open:[...document.querySelectorAll("details")].map(e=>e.open)})');result['route']=route
  results.append(result);print(json.dumps(result),flush=True);c.close()
 b.close()
(OUT/f'{engine}-{"candidate" if candidate else "live"}-regression.json').write_text(json.dumps(results,indent=2))
assert all(r['updates']>=2 for r in results), 'must exercise repeated actual native updates'
assert all(r['max']-r['min']<= (8 if engine=='webkit' and r['route']=='hardware-workloads' else 2) for r in results), 'idle mobile viewport moved during native refresh'
