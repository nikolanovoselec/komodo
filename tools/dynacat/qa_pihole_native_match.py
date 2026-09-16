"""Compare native Pi-hole chart to captured live Proxmox styling; never deploys.
Run --mode live for strict pre-implementation RED; --mode candidate uses the
existing captured-real test_networking_lower.page renderer fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'pihole-size-qa'
MEASURE = r'''root => {
 const box=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}};
 const inspect=e=>{if(!e)return null;const s=getComputedStyle(e);return {tag:e.tagName,classes:e.getAttribute('class'),box:box(e),fill:s.fill,stroke:s.stroke,strokeWidth:s.strokeWidth,dash:s.strokeDasharray,opacity:s.opacity,fontSize:s.fontSize,lineHeight:s.lineHeight,display:s.display,gap:s.gap,marginTop:s.marginTop,viewBox:e.getAttribute('viewBox'),d:e.getAttribute('d'),text:e.textContent}};
 const svg=root.querySelector('svg');
 return {contentWidth:root.closest('.nw-pihole')?.querySelector('.nw-dns-body')?.getBoundingClientRect().width,root:inspect(root),svg:inspect(svg),axis:inspect(root.querySelector('.pve-netaxis')),rx:inspect(root.querySelector('.pve-rx')),tx:inspect(root.querySelector('.pve-tx')),grid:inspect(root.querySelector('.pve-gridline')),rxLabel:inspect(root.querySelector('.pve-rx-label')),txLabel:inspect(root.querySelector('.pve-tx-label')),areaCount:root.querySelectorAll('.nw-query-area').length,html:root.outerHTML,text:root.innerText,overflow:document.documentElement.scrollWidth>innerWidth};
}'''


def capture(browser, url, prefix, reference=False):
    rows = []
    for width in (1600, 390):
        for theme, key in (('dark', 'midnight-navy'), ('light', 'catppuccin-latte')):
            context = browser.new_context(viewport={'width':width,'height':1100}, device_scale_factor=1, is_mobile=width==390, has_touch=width==390, color_scheme=theme, service_workers='block')
            context.add_init_script("HTMLMediaElement.prototype.play=function(){return Promise.reject(new Error('QA blocks audio'))}")
            context.route('**/*', lambda r: r.abort() if r.request.resource_type=='media' or urlsplit(r.request.url).netloc != urlsplit(url).netloc else r.continue_())
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url)
            selector = '.pve-network' if reference else '.nw-pihole'
            page.locator(selector).first.wait_for(timeout=30000)
            page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
            page.wait_for_timeout(350)
            if not reference:
                page.locator('.nw-pihole svg').first.wait_for(timeout=30000)
            root = page.locator('.pve-network').first if reference else page.locator('.nw-pihole .pve-network, .nw-pihole .nw-query-chart').first
            row = root.evaluate(MEASURE)
            row.update(width=width,theme=theme,url=page.url,errors=errors)
            rows.append(row)
            stem = OUT / f'{prefix}-{theme}-{width}'
            page.screenshot(path=str(stem)+'-page.png', full_page=True)
            page.locator(selector).first.screenshot(path=str(stem)+'-card.png')
            root.screenshot(path=str(stem)+'-chart.png')
            if width == 390 and not reference:
                session=context.new_cdp_session(page)
                session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':195,'y':800}]})
                session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':195,'y':400}]})
                session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
                page.wait_for_timeout(1800)
                before=page.evaluate('scrollY')
                page.wait_for_timeout(4500)
                row['touchRefreshDrift']=page.evaluate('scrollY')-before
                assert abs(row['touchRefreshDrift'])<2
            context.close()
    (OUT / f'{prefix}-measurements.json').write_text(json.dumps(rows,indent=2))
    return rows


def compare(ref, target):
    failures=[]
    def check(ok, name):
        if not ok: failures.append(name)
    check('pve-network' in (target['root']['classes'] or '').split(), 'shared pve-network container')
    for name, cls in [('svg','pve-netgraph'),('axis','pve-netaxis'),('rx','pve-rx'),('tx','pve-tx'),('grid','pve-gridline'),('rxLabel','pve-rx-label'),('txLabel','pve-tx-label')]:
        item=target[name]
        check(item and cls in (item['classes'] or '').split(), 'shared '+cls)
    svg=target['svg']
    check(svg and svg['viewBox']=='0 0 100 30', 'viewBox 0 0 100 30')
    check(svg and svg['box']['height']>=140, 'large chart height at least 140px')
    ratio=svg['box']['width']/target['contentWidth'] if svg else 0
    check(.5<=ratio<=.7 if target['width']>700 else .95<=ratio<=1.01, 'desktop chart 50–70% content width; mobile full width')
    check(target['areaCount']==0, 'no area fills')
    check(target['grid'] and target['grid']['d']==ref['grid']['d'], 'exact native three-line grid geometry')
    if svg and ref['svg']:
        for prop in ('display','marginTop'):
            check(svg[prop]==ref['svg'][prop], 'svg.'+prop+' native match')
    for name in ('rx','tx','grid'):
        if target[name] and ref[name]:
            for prop in ('fill','stroke','strokeWidth','dash','opacity'):
                check(target[name][prop]==ref[name][prop], f'{name}.{prop}: {target[name][prop]} != {ref[name][prop]}')
    for name in ('axis','rxLabel','txLabel'):
        if target[name] and ref[name]:
            for prop in ('fontSize','lineHeight','display','gap','marginTop'):
                check(target[name][prop]==ref[name][prop], f'{name}.{prop} native match')
    axis=target['axis']
    if axis and svg:
        check(axis['box']['y']>=svg['box']['bottom']-.1,'axis below plot')
        check('latest' in axis['text'].lower(),'latest endpoint in axis')
        for label,word in [('rxLabel','permitted'),('txLabel','blocked')]:
            item=target[label]
            check(item and word in item['text'].lower(), word+' semantic label')
            check(item and item['box']['y']>=axis['box']['bottom']-.1,word+' label beneath axis')
    check(not target['overflow'],'no horizontal viewport overflow')
    check(not target['errors'],'no browser errors')
    return failures


def compose(prefix, width, theme):
    files=[OUT/f'reference-{theme}-{width}-chart.png',OUT/f'{prefix}-{theme}-{width}-chart.png']
    images=[Image.open(p).convert('RGB') for p in files]
    canvas=Image.new('RGB',(sum(i.width for i in images)+30,max(i.height for i in images)+48),'#dddddd')
    draw=ImageDraw.Draw(canvas); x=10
    for label,img in zip(('LIVE PROXMOX REFERENCE',prefix.upper()+' PI-HOLE'),images):
        draw.text((x,8),label,fill='black');canvas.paste(img,(x,34));x+=img.width+10
    canvas.save(OUT/f'{prefix}-versus-reference-{theme}-{width}.png')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('live','candidate'),default='live')
    parser.add_argument('--reference-url',default='http://192.168.2.72:8080/hardware-workloads')
    parser.add_argument('--url',default='http://192.168.2.72:8080/networking')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    generator=None
    with sync_playwright() as p:
        browser=p.chromium.launch()
        refs=capture(browser,args.reference_url,'reference',True)
        if args.mode=='live':
            prefix='before';targets=capture(browser,args.url,prefix)
        browser.close()
    if args.mode=='candidate':
        import test_networking_lower as tests
        tests.OUT=OUT/'fixture'
        generator=tests.page.__wrapped__()
        try:
            page=next(generator)
            prefix='candidate';targets=capture(page.context.browser,'http://127.0.0.1:18146/networking',prefix)
        finally:
            generator.close()
    checks=[]
    for ref,target in zip(refs,targets):
        failures=compare(ref,target)
        checks.append({'width':target['width'],'theme':target['theme'],'failures':failures})
        compose(prefix,target['width'],target['theme'])
    source=Path('/tmp/network-query-current.json')
    report={'mode':args.mode,'status':'RED' if any(c['failures'] for c in checks) else 'GREEN','checks':checks,'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None}
    (OUT/f'{prefix}-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return int(report['status']=='RED')


if __name__=='__main__':
    raise SystemExit(main())
