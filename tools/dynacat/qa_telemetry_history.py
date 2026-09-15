"""Isolated live-source native renderer QA; no playback/download actions."""
import asyncio,json,subprocess,time
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
OUT=ROOT.parents[2]/'telemetry-history-qa'
def docker(*args):
 return subprocess.check_output(['docker',*args],text=True)
def prepare():
 OUT.mkdir(exist_ok=True);(OUT/'config').mkdir(exist_ok=True);(OUT/'state').mkdir(exist_ok=True)
 spec=json.loads(docker('inspect','media-stage-workload-summary'))[0]
 env=spec['Config']['Env'];args=[]
 for e in env:args+=['-e',e]
 for name in ['telemetry-history-adapter','telemetry-history-renderer']:
  subprocess.run(['docker','rm','-f',name],capture_output=True)
 docker('run','-d','--name','telemetry-history-adapter','--network','media-compact-qa',*args,'-e','WORKLOAD_HISTORY_PATH=/state/workloads.sqlite','-e','MEDIA_HISTORY_PATH=/state/media.sqlite','-v',f'{OUT}/state:/state','-v',f'{ROOT}/adapter:/app:ro',spec['Config']['Image'],'python','-B','/app/adapter.py')
 config=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
 widgets=[w for c in config['pages'][0]['columns'] for w in c['widgets'] if w.get('title') in ['Workloads','Proxmox Cluster']]
 media=next(w for page in config['pages'] for c in page['columns'] for w in c['widgets'] if w.get('title')=='Media')
 template=media['template'];start=template.index('{{ if not (.JSON.String "resources.error") }}<section class="mo-traffic"');end=template.index('</section>{{ end }}',start)+len('</section>{{ end }}')
 widgets.append(dict(type='custom-api',title='Media host history',url=media['url'],cache='1s',template=template[start:end]))
 for w in widgets:
  w['url']=w['url'].replace('workload-summary','telemetry-history-adapter')
 config['pages']=[dict(name='History QA',slug='history',columns=[dict(size='full',widgets=[dict(type='html',source='<p>LIVE SOURCE · ISOLATED 30-MINUTE TELEMETRY QA · NO PLAYBACK</p>')]+widgets)])]
 config['document']['head']+='<link rel="stylesheet" href="/assets/telemetry-history.css">'
 config['server']['port']=8080;config['server']['cache-dir']='/tmp/cache'
 (OUT/'config/dynacat.yml').write_text(yaml.safe_dump(config,sort_keys=False))
 docker('run','-d','--name','telemetry-history-renderer','--network','media-compact-qa','-p','127.0.0.1:18131:8080','-v',f'{OUT}/config:/app/config:ro','-v',f'{ROOT}/assets:/app/assets:ro','panonim/dynacat:3.0.0')
async def verify():
 async with async_playwright() as p:
  browser=await p.chromium.launch();page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://127.0.0.1:18131/history');await page.wait_for_selector('.cw-history-chart',timeout=90000)
  report=[]
  for theme in ['midnight-navy','catppuccin-latte']:
   await page.locator(f'.theme-choices [data-key="{theme}"]').first.evaluate('e=>e.click()');await page.wait_for_timeout(500)
   for width in [1600,390]:
    await page.set_viewport_size({'width':width,'height':1100});await page.wait_for_timeout(300)
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
    count=await page.locator('.cw-history-chart').count();assert count>0
    assert await page.locator('.cw-history-line').evaluate_all('els=>els.some(e=>e.getAttribute("d").length>0)')
    assert await page.locator('.cw-workload meter').count()==0
    await page.screenshot(path=str(OUT/f'live-{theme}-{width}.png'),full_page=True)
    report.append(dict(theme=theme,width=width,graphs=count))
  details=page.locator('.cw-docker').first
  await details.locator('summary').click();await page.wait_for_timeout(1600);assert await details.evaluate('e=>e.open')
  assert not errors,errors
  (OUT/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));await browser.close()
if __name__=='__main__':
 prepare();asyncio.run(verify())
