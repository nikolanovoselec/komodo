"""Isolated native-template delivery QA. Synthetic data is explicitly labelled; no live writes.
Run with QA venv Python qa_delivery.py [--prepare-only]. Evidence stays outside repository.
"""
import asyncio, copy, json, subprocess, sys
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
ROOT = Path(__file__).parent
OUT = ROOT.parents[2] / 'delivery-qa-evidence'


def prepare():
    OUT.mkdir(exist_ok=True)
    (OUT / 'config').mkdir(exist_ok=True)
    (OUT / 'source').mkdir(exist_ok=True)
    config = yaml.safe_load((ROOT / 'config/dynacat.yml').read_text())
    media = next(p for p in config['pages'] if p.get('slug') == 'media')
    widgets = [copy.deepcopy(w) for c in media['columns'] for w in c['widgets'] if w.get('title') in ('Sonarr delivery', 'Radarr delivery')]
    data = {}
    for app in ('sonarr', 'radarr'):
        item = dict(title='SYNTHETIC · A deliberately long delivery title with enough words to wrap safely', url=f'https://{app}.graymatter.ch/{"series/example" if app == "sonarr" else "movie/example"}', imdb='https://www.imdb.com/title/tt0000001/', progress=37.5, status='downloading', tracked='Downloading', remaining_gb=4.25, eta='00:12:34', subtitle='Synthetic completed import', quality='WEB-1080p', date='2026-09-15T12:00:00Z')
        missing = dict(item, title='SYNTHETIC · Source URL unavailable', url='', imdb='', eta='', progress=0)
        data[app] = dict(age=17, error='', data=dict(total=2, queue=[item, missing], recent=[item, missing], truncated=True))
    (OUT / 'source/media-arr').write_text(json.dumps(data))
    for w in widgets:
        w['url'] = 'http://delivery-qa-source:8090/media-arr'
        w['cache'] = '1s'
        w['template'] = '<p>SYNTHETIC DELIVERY FIXTURE · NOT LIVE</p>' + w['template']
    state_widgets = []
    for state in ('empty', 'error'):
        state_data = copy.deepcopy(data)
        for value in state_data.values():
            value['data'].update(queue=[], recent=[], total=0, truncated=False)
            if state == 'error':
                value['error'] = 'SYNTHETIC API unavailable'
        (OUT / f'source/{state}').write_text(json.dumps(state_data))
        for widget in widgets:
            extra = copy.deepcopy(widget)
            extra['url'] = f'http://delivery-qa-source:8090/{state}'
            extra['css-class'] = f'delivery-qa-{state}'
            state_widgets.append(extra)
    config['pages'] = [dict(name='Delivery QA', slug='media', columns=[dict(size='full', widgets=[dict(type='html', source='<p>SYNTHETIC DELIVERY QA · sidebar layout · no playback or download controls</p>')]), dict(size='small', widgets=widgets + state_widgets)])]
    config['document']['head'] = '<link rel="stylesheet" href="/assets/media-ops.css"><script defer src="/assets/media-ops.js"></script>'
    config['theme'].pop('custom-css-file', None)
    config['server']['port'] = 8080
    config['server']['cache-dir'] = '/tmp/cache'
    (OUT / 'config/dynacat.yml').write_text(yaml.safe_dump(config, sort_keys=False))
    def docker(*args):
        return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout
    for name in ('delivery-qa-stage', 'delivery-qa-source'):
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
    docker('run','-d','--name','delivery-qa-source','--network','media-compact-qa','-v',f'{OUT}/source:/data:ro','-w','/data','python:3.13-slim','python','-m','http.server','8090')
    docker('run','-d','--name','delivery-qa-stage','--network','media-compact-qa','-p','127.0.0.1:18129:8080','-v',f'{OUT}/config:/app/config:ro','-v',f'{ROOT}/assets:/app/assets:ro','panonim/dynacat:3.0.0')


async def verify():
    reports = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for width in (360, 390, 1600):
            for light in (False, True):
                page = await browser.new_page(viewport={'width': width, 'height': 1000}, is_mobile=width<600, has_touch=width<600)
                await page.goto('http://127.0.0.1:18129/media')
                await page.wait_for_selector('.mo-download')
                await page.add_style_tag(content='*{scroll-behavior:auto!important}')
                if light:
                    await page.locator('.theme-choices [data-key="catppuccin-latte"]').first.evaluate('e=>e.click()')
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'Page overflows'
                assert await page.locator('.mo-imports summary>span').first.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)>=13'), 'History label too small'
                assert not await page.locator('.mo-imports').first.evaluate('e=>e.open')
                await page.screenshot(path=str(OUT / f'collapsed-{width}-{"light" if light else "dark"}.png'), full_page=True)
                await page.locator('.mo-imports').evaluate_all('els=>els.forEach(e=>e.open=true)')
                queue = page.locator('.mo-download').first
                assert await queue.locator('.mo-download-meta').count() == 1, 'Status, remaining and ETA need a distinct readable metadata row'
                assert await queue.locator('.mo-download-progress').inner_text() == '37.5%'
                assert await queue.locator('.mo-download-meta').inner_text() == 'downloading · Downloading\n4.25 GB left\nETA 00:12:34'
                assert await page.locator('.mo-download').nth(1).locator('.mo-download-meta').inner_text() == 'downloading · Downloading\n4.25 GB left\nETA unavailable'
                assert await queue.locator('strong').evaluate("e=>parseFloat(getComputedStyle(e).fontSize)>=14")
                assert await queue.locator('.mo-progress i').evaluate("e=>e.style.width==='37.5%'")
                for selector in ('.mo-download', '.mo-import'):
                    for idx in (0, 2):
                        row = page.locator(selector).nth(idx)
                        await row.evaluate("e=>e.scrollIntoView({block:'center'})")
                        result = await row.evaluate('''e => {
                          const a=e.querySelector('a.mo-item-title'), b=e.getBoundingClientRect();
                          const points=[[3,3],[b.width-3,3],[3,b.height-3],[b.width-3,b.height-3],[b.width/2,b.height/2]];
                          return {url:a.getAttribute('href'), label:a.getAttribute('aria-label'), hits:points.map(([x,y])=>{const hit=document.elementFromPoint(b.x+x,b.y+y)?.closest('a');return hit===a||hit?.classList.contains('mo-imdb')}), nested:!!e.querySelector('a a'), width:b.width, height:b.height};
                        }''')
                        assert all(result['hits']), ('Entire cell must target existing source URL', selector, width, result)
                        assert result['label'] and not result['nested'], result
                        app = 'sonarr' if idx == 0 else 'radarr'
                        expected = json.loads((OUT / 'source/media-arr').read_text())[app]['data']['queue'][0]['url']
                        assert result['url'] == expected, 'Source URL changed'
                        box = await row.bounding_box()
                        await page.evaluate("window.deliveryClicks=[]; document.addEventListener('click',e=>{const a=e.target.closest('a');if(a){e.preventDefault();window.deliveryClicks.push(a.getAttribute('href'))}}, {once:true})")
                        await page.mouse.click(box['x'] + 3, box['y'] + 3)
                        assert await page.evaluate('window.deliveryClicks') == [expected], 'Corner click did not activate source link'
                        imdb = row.locator('.mo-imdb')
                        await imdb.click(trial=True)
                        await row.locator('a.mo-item-title').focus()
                        await page.keyboard.press('Tab')
                        await page.keyboard.press('Shift+Tab')
                        assert await row.locator('a.mo-item-title').evaluate("e=>e===document.activeElement && getComputedStyle(e,'::after').outlineStyle !== 'none'"), 'Missing keyboard focus outline'
                        reports.append(dict(viewport=width, light=light, selector=selector, **result))
                    missing = page.locator(selector).nth(1)
                    assert await missing.locator('a.mo-item-title').count() == 0
                    assert 'Source link unavailable' in await missing.inner_text()
                assert await page.locator('.delivery-qa-empty .mo-download, .delivery-qa-error .mo-download').count() == 0
                assert await page.locator('.delivery-qa-empty .mo-empty').count() == 4
                assert await page.locator('.delivery-qa-error .mo-notice').all_text_contents() == ['SYNTHETIC API unavailable'] * 2
                assert await page.locator('.mo-arr-delivery .mo-section small').count() == 0
                await page.screenshot(path=str(OUT / f'delivery-{width}-{"light" if light else "dark"}.png'), full_page=True)
                await page.close()
        await browser.close()
    (OUT / 'report.json').write_text(json.dumps(reports, indent=2))
    print(f'PASS: {len(reports)} row/theme/viewport full-cell hit and keyboard checks')

if __name__ == '__main__':
    prepare()
    if '--prepare-only' not in sys.argv:
        asyncio.run(verify())
