"""Isolated native renderer; captured actual ARR imports, synthetic queue explicitly separate."""
import asyncio,copy,json,subprocess,sys
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
OUT=ROOT.parents[1]/'arr-thumbnail-qa'
def docker(*a):return subprocess.run(['docker',*a],check=True,capture_output=True,text=True).stdout.strip()
def prepare(baseline=False):
    (OUT/'config').mkdir(exist_ok=True)
    (OUT/'source').mkdir(exist_ok=True)
    data=json.loads((OUT/'captured-arr.json').read_text())
    (OUT/'source/captured').write_text(json.dumps(data))
    fixture=copy.deepcopy(data)
    for app,v in fixture.items():
        row=copy.deepcopy(next(r for r in v['data']['recent'] if r['poster']))
        row.update(title='SYNTHETIC queue test',progress=37.5,status='downloading',tracked='Downloading',remaining_gb=4.25,eta='00:12:34')
        v['data'].update(queue=[row,dict(row,poster='',imdb='',url='')],total=2)
    (OUT/'source/fixture').write_text(json.dumps(fixture))
    d=yaml.safe_load((OUT/'before-config.yml' if baseline else ROOT/'config/dynacat.yml').read_text())
    widgets=[w for p in d['pages'] for c in p['columns'] for w in c['widgets'] if w.get('title') in ('Sonarr delivery','Radarr delivery')]
    for w in widgets:w.update(url='http://arr-thumb-source:8090/captured',cache='1s',**{'update-interval':'2s'})
    f=copy.deepcopy(widgets)
    for w in f:w.update(url='http://arr-thumb-source:8090/fixture')
    d['pages']=[dict(name='ARR preview',slug='media',columns=[dict(size='full',widgets=[dict(type='html',source='<p>CAPTURED REAL ARR DATA · STAGED PREVIEW · NOT DEPLOYED</p>')]),dict(size='small',widgets=widgets)]),dict(name='Synthetic queue tests',slug='fixture',columns=[dict(size='full',widgets=[dict(type='html',source='<p>SYNTHETIC QUEUE TEST · NOT LIVE</p>')]),dict(size='small',widgets=f)])]
    d['document']['head']='<link rel="stylesheet" href="/assets/media-ops.css"><script defer src="/assets/media-ops.js"></script>'
    d['theme'].pop('custom-css-file',None);d['server'].update(port=8080,**{'cache-dir':'/tmp/cache'})
    (OUT/'config/dynacat.yml').write_text(yaml.safe_dump(d,sort_keys=False))
    for name in ('arr-thumb-stage','arr-thumb-source'):subprocess.run(['docker','rm','-f',name],capture_output=True)
    docker('run','-d','--name','arr-thumb-source','--network','media-compact-qa','-v',f'{OUT}/source:/data:ro','-w','/data','python:3.13-slim','python','-m','http.server','8090')
    docker('run','-d','--name','arr-thumb-stage','--network','media-compact-qa','-p','127.0.0.1:18139:8080','-v',f'{OUT}/config:/app/config:ro','-v',f'{ROOT}/assets:/app/assets:ro','panonim/dynacat:3.0.0')
async def verify():
    captured=json.loads((OUT/'captured-arr.json').read_text());report=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for width in (1600,390):
            for light in (False,True):
                page=await b.new_page(viewport=dict(width=width,height=1200),is_mobile=width==390,has_touch=width==390)
                await page.goto('http://127.0.0.1:18139/media');await page.wait_for_selector('.mo-import')
                if light:
                    await page.locator('[data-key="catppuccin-latte"]').first.evaluate('e=>e.click()')
                    await page.wait_for_function('()=>document.documentElement.dataset.scheme==="light"')
                await page.add_style_tag(content='*{scroll-behavior:auto!important;animation:none!important}')
                await page.evaluate('document.addEventListener("click",e=>{let a=e.target.closest("article a");if(a){e.preventDefault();window.lastClick=a.getAttribute("href")}})')
                for i,app in enumerate(('sonarr','radarr')):
                    w=page.locator('.mo-arr-delivery').nth(i)
                    assert await w.locator('.mo-import:visible').count()==3
                    await w.scroll_into_view_if_needed()
                    await page.screenshot(path=str(OUT/f'{width}-{"light" if light else "dark"}-{app}.png'),clip=await w.bounding_box())
                    await w.locator('summary').focus();await page.keyboard.press('Enter')
                    assert await w.locator('details').evaluate('e=>e.open')
                    for j,r in enumerate(captured[app]['data']['recent']):
                        row=w.locator('.mo-import').nth(j)
                        await row.evaluate('e=>e.scrollIntoView({block:"center"})')
                        a=row.locator('.mo-item-title');thumb=row.locator('.mo-arr-thumb')
                        assert await a.get_attribute('href')==r['url'], (app,j,await a.get_attribute('href'),r['url'])
                        assert await thumb.get_attribute('href')==r['imdb']
                        assert await row.locator('time').text_content()==r['date']
                        assert await row.locator('p').text_content()==r['subtitle']
                        assert await row.locator('a a').count()==0
                        if r['poster']:
                            assert await thumb.locator('img').get_attribute('src')=='data:'+r.get('poster_mime','image/jpeg')+';base64,'+r['poster']
                            await thumb.locator('img').evaluate('e=>e.decode()'); assert await thumb.locator('img').evaluate('e=>e.naturalWidth>0')
                        else:assert await thumb.locator('.mo-arr-thumb-fallback').count()==1
                        assert await row.evaluate('''e=>{let r=e.getBoundingClientRect(),a=e.querySelector('.mo-item-title');return [[3,3],[r.width-3,3],[3,r.height-3],[r.width-3,r.height-3],[r.width/2,r.height/2]].every(([x,y])=>{let h=document.elementFromPoint(r.x+x,r.y+y)?.closest('a');return h===a||h?.classList.contains('mo-arr-thumb')})}''')
                        hit=await thumb.evaluate('e=>{let r=e.getBoundingClientRect();return {w:r.width,h:r.height,hit:document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.outerHTML.slice(0,150),ok:r.width>=44&&r.height>=44&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest("a")===e}}')
                        assert hit['ok'],(width,light,app,j,hit)
                        box=await row.bounding_box();await page.mouse.click(box['x']+3,box['y']+3);assert await page.evaluate('window.lastClick')==r['url']
                        await thumb.click();assert await page.evaluate('window.lastClick')==r['imdb']
                        await a.focus();await page.keyboard.press('Tab');assert await thumb.evaluate('e=>document.activeElement===e')
                        await page.keyboard.press('Enter');assert await page.evaluate('window.lastClick')==r['imdb']
                    await w.locator('summary').focus();await page.keyboard.press('Enter');await w.locator('details:not([open])').wait_for(state='attached')
                    report.append(dict(width=width,light=light,app=app,rows=len(captured[app]['data']['recent'])))
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.goto('http://127.0.0.1:18139/fixture');await page.wait_for_selector('.mo-download')
                row=page.locator('.mo-download').first
                assert await row.locator('.mo-arr-thumb img').count()==1
                assert await row.locator('.mo-download-progress').inner_text()=='37.5%'
                assert 'ETA 00:12:34' in await row.inner_text()
                assert await page.locator('.mo-download').nth(1).locator('a').count()==0
                await page.evaluate('document.addEventListener("click",e=>{let a=e.target.closest("article a");if(a){e.preventDefault();window.lastClick=a.href}})')
                for n in (0,2):
                    q=page.locator('.mo-download').nth(n);await q.scroll_into_view_if_needed()
                    source=q.locator('.mo-item-title');thumb=q.locator('.mo-arr-thumb')
                    assert await q.evaluate('e=>{let r=e.getBoundingClientRect();return [[3,3],[r.width-3,r.height-3],[r.width/2,r.height/2]].every(([x,y])=>document.elementFromPoint(r.x+x,r.y+y)?.closest("a")===e.querySelector(".mo-item-title"))}')
                    box=await q.bounding_box();await page.mouse.click(box['x']+3,box['y']+3);assert await page.evaluate('window.lastClick')==await source.get_attribute('href')
                    await thumb.click();assert await page.evaluate('window.lastClick')==await thumb.get_attribute('href')
                    await source.focus();await page.keyboard.press('Tab');assert await thumb.evaluate('e=>document.activeElement===e')
                    assert await thumb.evaluate('e=>e.offsetWidth>=44&&e.offsetHeight>=44')
                await page.close()
        await b.close()
    (OUT/'report.json').write_text(json.dumps(report,indent=2));print('PASS',report)
if __name__=='__main__':
    if '--prepare' in sys.argv:prepare('--baseline' in sys.argv)
    else:asyncio.run(verify())
