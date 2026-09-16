"""Native two-chart acceptance: captured real source, desktop and touch mobile."""
import json, sys, time, subprocess, copy
from pathlib import Path
import yaml
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'pihole-split-qa'
NAMES=('pihole-split-renderer','pihole-split-source')
def docker(*args): return subprocess.check_output(['docker',*args],text=True).strip()
def capture(url,prefix):
    reports=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for width in (1600,390):
            for theme,key in [('dark','midnight-navy'),('light','catppuccin-latte')]:
                c=browser.new_context(viewport={'width':width,'height':1100},is_mobile=width==390,has_touch=width==390,color_scheme=theme)
                c.add_init_script("HTMLMediaElement.prototype.play=()=>Promise.reject(new Error('QA blocks audio'))")
                page=c.new_page(); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url);page.locator('.nw-pihole').wait_for()
                page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
                page.wait_for_timeout(400)
                page.locator('.nw-pihole').screenshot(path=str(OUT/f'{prefix}-{theme}-{width}.png'))
                plots=page.locator('.nw-dns-plot'); assert plots.count()==2,'Two separate plots required'
                assert plots.locator('h4').all_text_contents()==['REQUESTS','BLOCKS']
                assert 'Permitted' not in page.locator('.nw-dns-network').inner_text()
                body=page.locator('.nw-dns-body').bounding_box();chart=page.locator('.nw-dns-network').bounding_box()
                ratio=chart['width']/body['width']; assert (.5<=ratio<=.7) if width==1600 else (.99<=ratio<=1.01)
                sizes=[]
                for plot in plots.all():
                    b=plot.locator('svg').bounding_box();sizes.append(b); assert 140<=b['height']<=180
                    assert plot.locator('.nw-query-line').count()==1 and plot.locator('.nw-query-area').count()==1
                    assert 'queries / 10 min' in plot.inner_text()
                    assert float(plot.locator('.nw-query-area').evaluate('e=>getComputedStyle(e).fillOpacity'))>=.35
                assert sizes[1]['y']>=sizes[0]['y']+sizes[0]['height']
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert not page.locator('.nw-dns-network *').evaluate_all('es=>es.some(e=>{const r=e.getBoundingClientRect();return r.width&&(r.right>innerWidth+1||r.left<0)})')
                assert page.locator('.nw-infrastructure').bounding_box()['y']>=page.locator('.nw-pihole').bounding_box()['y']+page.locator('.nw-pihole').bounding_box()['height']
                assert page.locator('.nw-resolver').count()==2
                drift=None
                if width==390:
                    s=c.new_cdp_session(page)
                    for typ,pts in [('touchStart',[{'x':195,'y':900}]),('touchMove',[{'x':195,'y':400}]),('touchEnd',[])]:s.send('Input.dispatchTouchEvent',{'type':typ,'touchPoints':pts})
                    page.wait_for_timeout(1800);before=page.evaluate('scrollY')
                    # Exercise changed native refresh in staging; live waits over its 10s interval.
                    source=OUT/'source/network-current'
                    if prefix=='candidate':
                        data=json.loads(source.read_text());data['pihole']['total_queries']+=1;source.write_text(json.dumps(data))
                    page.wait_for_timeout(12500);drift=page.evaluate('scrollY')-before;assert abs(drift)<2
                assert not errors
                reports.append(dict(width=width,theme=theme,plots=sizes,chartRatio=ratio,touchRefreshDrift=drift,errors=errors))
                c.close()
        browser.close()
    (OUT/f'{prefix}-report.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
def stage():
    cfg=yaml.safe_load((ROOT/'config/dynacat.yml').read_text());page=copy.deepcopy(next(p for p in cfg['pages'] if p.get('slug')=='networking'))
    for col in page['columns']:
        col['widgets']=[w for w in col['widgets'] if 'network-current' in w.get('url','')]
        for w in col['widgets']:w.update(url='http://pihole-split-source:8090/network-current',cache='1s',**{'update-interval':'2s'})
    page['columns']=[c for c in page['columns'] if c['widgets']];cfg['pages']=[page];cfg['server'].update(port=8080,**{'cache-dir':'/tmp/cache'})
    (OUT/'config').mkdir(exist_ok=True);(OUT/'config/dynacat.yml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    docker('run','-d','--name',NAMES[1],'--network','media-compact-qa','-v',f'{OUT}/source:/data:ro','-w','/data','python:3.13-slim','python','-m','http.server','8090')
    docker('run','-d','--name',NAMES[0],'--network','media-compact-qa','-p','127.0.0.1:18149:8080','-v',f'{OUT}/config:/app/config:ro','-v',f'{ROOT}/assets:/app/assets:ro','panonim/dynacat:3.0.0')
if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    if sys.argv[1]=='candidate':
        try:
            stage()
            import urllib.request
            for i in range(30):
                try:urllib.request.urlopen('http://127.0.0.1:18149/networking');break
                except Exception:time.sleep(.3)
            capture('http://127.0.0.1:18149/networking','candidate')
        finally:
            for name in NAMES:subprocess.run(['docker','rm','-f',name],capture_output=True)
    else:capture('http://192.168.2.72:8080/networking',sys.argv[1])
