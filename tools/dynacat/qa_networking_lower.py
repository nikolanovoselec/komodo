"""Native captured-real screenshots and release verification. Never deploys.
NETWORK_QA_SOURCE=/absolute/captured/network-current python qa_networking_lower.py
After release: same command with --url http://127.0.0.1:TUNNEL/networking
Input must contain actual captured query_history to verify a populated chart.
"""
import argparse
import hashlib
import json
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
import test_networking_lower as tests


def capture(browser, url, variant):
    source=json.loads(tests.SOURCE.read_text())
    report={'source':str(tests.SOURCE),'sourceType':'captured-real' if variant=='candidate' else 'live',
            'sourceSha256':hashlib.sha256(tests.SOURCE.read_bytes()).hexdigest(),'measurements':[]}
    for width in (1600,390):
        for theme,key in (('dark','midnight-navy'),('light','catppuccin-latte')):
            context=browser.new_context(viewport={'width':width,'height':1100},is_mobile=width==390,has_touch=width==390,device_scale_factor=1,color_scheme=theme,service_workers='block')
            context.add_init_script("HTMLMediaElement.prototype.play=function(){return Promise.reject(new Error('QA blocks audio'))}")
            context.route('**/*',lambda route: route.abort() if route.request.resource_type=='media' or urlsplit(route.request.url).netloc!=urlsplit(url).netloc else route.continue_())
            page=context.new_page(); errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url);page.locator('.nw-pihole').wait_for()
            if variant=='live': page.locator('.nw-query-chart svg').wait_for(timeout=30000)
            page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
            page.wait_for_timeout(250)
            tests.test_clients_removed_and_pihole_full_width_below_preserved_infrastructure(page) if variant=='candidate' else None
            assert page.locator('.nw-connected,.nw-dns-history,.nw-dns-query').count()==0
            h=source.get('pihole',{}).get('query_history',{})
            paths={}
            if variant=='candidate' and h.get('available'):
                for kind in ('permitted','blocked'):
                    for cls,field in (('line','path'),('area','area_path')):
                        actual=page.locator(f'.nw-query-{cls}[data-series="{kind}"]').get_attribute('d')
                        assert actual==h[kind][field]
                        paths[kind+'_'+field]=actual
            elif variant=='candidate':
                assert page.locator('.nw-query-unavailable').count()==1
            else:
                assert page.locator('.nw-query-chart svg').count()==1, 'Live history chart is unavailable'
                for kind in ('permitted','blocked'):
                    for cls in ('line','area'):
                        assert page.locator(f'.nw-query-{cls}[data-series="{kind}"]').get_attribute('d')
                a=page.locator('.nw-infrastructure').bounding_box(); b=page.locator('.nw-pihole').bounding_box()
                assert abs(a['width']-b['width'])<2 and b['y']>=a['y']+a['height']
            if width==390:
                session=context.new_cdp_session(page)
                session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':195,'y':850}]})
                for y in (750,650,550,450,350):
                    session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':195,'y':y}]});page.wait_for_timeout(30)
                session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
                page.wait_for_timeout(1200)  # Wait for native touch inertia before measuring refresh stability.
                initial=page.evaluate('scrollY');assert initial>0
                page.wait_for_timeout(4500)
                assert abs(page.evaluate('scrollY')-initial)<3
                assert page.evaluate('matchMedia("(pointer:coarse)").matches')
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            prefix=tests.OUT/f'{variant}-{theme}-{width}'
            page.screenshot(path=str(prefix)+'-page.png',full_page=True)
            page.locator('.nw-pihole').screenshot(path=str(prefix)+'-pihole.png')
            m=page.evaluate('''()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,
              chartCount:document.querySelectorAll('.nw-query-chart svg').length,
              infrastructureHeight:document.querySelector('.nw-infrastructure').getBoundingClientRect().height,
              piholeWidth:document.querySelector('.nw-pihole').getBoundingClientRect().width,
              text:document.querySelector('.nw-pihole').innerText})''')
            m.update(theme=theme,errors=errors,paths=paths);assert not errors
            report['measurements'].append(m);context.close()
    report['passed']=True
    (tests.OUT/f'{variant}-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url');args=parser.parse_args()
    tests.OUT.mkdir(parents=True,exist_ok=True)
    generator=None
    try:
        if not args.url:
            generator=tests.page.__wrapped__();page=next(generator)
            capture(page.context.browser,'http://127.0.0.1:18146/networking','candidate')
        else:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                capture(browser,args.url,'live')
                browser.close()
    finally:
        if generator: generator.close()
