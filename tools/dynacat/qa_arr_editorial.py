"""Native ARR editorial comparison: captured actual responses, never live writes."""
import asyncio, json, subprocess, sys
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
import qa_delivery
ROOT=Path(__file__).parent
BASE=ROOT.parents[2]/'arr-editorial-baseline'
OUT=ROOT.parents[2]/'arr-editorial-evidence'

def stage(source):
    qa_delivery.prepare()
    captured=json.loads((BASE/'captured-arr.json').read_text())
    d=yaml.safe_load((source/'config/dynacat.yml').read_text())
    widgets=[w for p in d['pages'] for c in p['columns'] for w in c['widgets'] if w.get('title') in ('Sonarr delivery','Radarr delivery')]
    for w in widgets:
        w['url']='http://delivery-qa-source:8090/captured-arr'
    (qa_delivery.OUT/'source/captured-arr').write_text(json.dumps(captured))
    d['pages']=[dict(name='Delivery QA',slug='media',columns=[dict(size='full',widgets=[dict(type='html',source='<p>CAPTURED REAL DATA · ARR-only native comparison · NOT LIVE</p>')]),dict(size='small',widgets=widgets)])]
    d['document']['head']='<link rel="stylesheet" href="/assets/media-ops.css"><script defer src="/assets/media-ops.js"></script>'
    d['theme'].pop('custom-css-file',None)
    d['server'].update(port=8080,**{'cache-dir':'/tmp/cache'})
    (qa_delivery.OUT/'config/dynacat.yml').write_text(yaml.safe_dump(d,sort_keys=False))
    subprocess.run(['docker','rm','-f','delivery-qa-stage'],check=True,capture_output=True)
    subprocess.run(['docker','run','-d','--name','delivery-qa-stage','--network','media-compact-qa','-p','127.0.0.1:18129:8080','-v',f'{qa_delivery.OUT}/config:/app/config:ro','-v',f'{source}/assets:/app/assets:ro','panonim/dynacat:3.0.0'],check=True,capture_output=True)

async def verify(label):
    OUT.mkdir(exist_ok=True)
    report=[]
    captured=json.loads((BASE/'captured-arr.json').read_text())
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in (390,1600):
            for light in (False,True):
                page=await browser.new_page(viewport={'width':width,'height':1200},is_mobile=width<600,has_touch=width<600)
                await page.goto('http://127.0.0.1:18129/media')
                await page.wait_for_selector('.mo-arr-delivery')
                if light: await page.locator('.theme-choices [data-key="catppuccin-latte"]').first.evaluate('e=>e.click()')
                await page.add_style_tag(content='*{animation:none!important;transition:none!important;scroll-behavior:auto!important}')
                for i,app in enumerate(('sonarr','radarr')):
                    w=page.locator('.mo-arr-delivery').nth(i)
                    await w.screenshot(path=str(OUT/f'{label}-{width}-{light}-{app}.png'))
                    dims=await w.evaluate('e=>({height:e.getBoundingClientRect().height,rows:[...e.querySelectorAll(".mo-import")].filter(x=>x.checkVisibility()).map(x=>x.getBoundingClientRect().height),visible:[...e.querySelectorAll(".mo-import")].filter(x=>x.checkVisibility()).length})')
                    report.append(dict(width=width,light=light,app=app,**dims))
                    if label=='baseline':continue
                    assert dims['visible']==min(3,len(captured[app]['data']['recent'])), 'Recent activity must be useful without opening history'
                    assert max(dims['rows'])<=105 and dims['height']<=450, 'Editorial rows and complete default section must be compact'
                    assert await w.locator('.mo-section').evaluate('e=>e.getBoundingClientRect().height<=30'), 'One-line app header'
                    assert await w.locator('.mo-delivery-summary').count()==0, 'Remove oversized empty queue panel'
                    assert await w.locator('.mo-import').count()==len(captured[app]['data']['recent']), 'No duplicated history rows'
                    assert await w.evaluate('e=>getComputedStyle(e.querySelector("summary>span")).color===getComputedStyle(e.querySelector("h3")).color'), 'History action must not use subdued disabled-looking text'
                    summary=w.locator('summary')
                    await summary.focus();await page.keyboard.press('Enter')
                    assert await w.locator('details').evaluate('e=>e.open')
                    assert await summary.bounding_box() is not None
                    await page.keyboard.press('Space')
                    assert not await w.locator('details').evaluate('e=>e.open')
                    await w.locator('details').evaluate('e=>e.open=true')
                    for j,rowdata in enumerate(captured[app]['data']['recent']):
                        row=w.locator('.mo-import').nth(j)
                        await row.evaluate('e=>e.scrollIntoView({block:"center"})')
                        assert await row.evaluate('''e=>{const a=e.querySelector('.mo-item-title'),r=e.getBoundingClientRect();return [[3,3],[r.width-3,3],[3,r.height-3],[r.width-3,r.height-3],[r.width/2,r.height/2]].every(([x,y])=>{const h=document.elementFromPoint(r.x+x,r.y+y)?.closest('a');return h===a||h?.classList.contains('mo-imdb')})}'''), (app,j,'row hit')
                        imdb=row.locator('.mo-imdb')
                        assert await imdb.evaluate('e=>getComputedStyle(e).color===getComputedStyle(e.closest("article").querySelector("p")).color'), 'IMDb action must be readable, not subdued'
                        assert await imdb.get_attribute('href')==rowdata['imdb']
                        assert await imdb.evaluate('e=>{const r=e.getBoundingClientRect();return r.width>=44&&r.height>=44&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===e}'), (app,j,'independent IMDb')
                        assert await row.locator('.mo-item-title').get_attribute('href')==rowdata['url']
                        assert await row.locator('p').text_content()==str(rowdata['subtitle']), (app,j,await row.locator('p').text_content(),rowdata)
                        assert await row.locator('time').text_content()==rowdata['date']
                    await w.locator('details').evaluate('e=>e.open=true')
                    await w.screenshot(path=str(OUT/f'{label}-{width}-{light}-{app}-expanded.png'))
                if label=='candidate' and width==1600 and not light:
                    source=qa_delivery.OUT/'source/captured-arr'
                    original=source.read_text()
                    changed=json.loads(original)
                    for value in changed.values():
                        value['data']['recent'][0]['subtitle']=str(value['data']['recent'][0]['subtitle'])+' [REFRESH FIXTURE]'
                    await page.locator('.mo-arr-delivery').first.locator('.mo-item-title').first.focus()
                    source.write_text(json.dumps(changed))
                    await page.wait_for_function('()=>[...document.querySelectorAll(".mo-recent-preview p")].filter(e=>e.textContent.includes("[REFRESH FIXTURE]")).length===2',timeout=30000)
                    assert await page.locator('.mo-imports').evaluate_all('es=>es.every(e=>e.open)'), 'Expanded state lost'
                    assert await page.locator('.mo-arr-delivery').first.locator('.mo-item-title').first.evaluate('e=>e===document.activeElement'), 'Focused source link lost'
                    await page.locator('.mo-imports').evaluate_all('es=>es.forEach(e=>e.open=false)')
                    for value in changed.values(): value['data']['recent']=value['data']['recent'][:4]
                    source.write_text(json.dumps(changed))
                    await page.wait_for_function('()=>document.querySelectorAll(".mo-import").length===8',timeout=30000)
                    assert await page.locator('.mo-imports').evaluate_all('es=>es.every(e=>!e.open)'), 'Collapsed state lost'
                    assert await page.locator('.mo-history-count').all_text_contents()==['1 more ⌄','1 more ⌄']
                    source.write_text(original)
                    await page.wait_for_function('()=>document.querySelectorAll(".mo-import").length===24',timeout=30000)
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.close()
        await browser.close()
    (OUT/f'{label}.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

if __name__=='__main__':
    label=sys.argv[1] if len(sys.argv)>1 else 'candidate'
    stage(BASE if label=='baseline' else ROOT)
    asyncio.run(verify(label))
