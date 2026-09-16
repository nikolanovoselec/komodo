"""Read-only live evidence and captured-real native cohesive redesign acceptance."""
import argparse, copy, hashlib, json, re, subprocess, time, urllib.request
from pathlib import Path
from collections import Counter
import yaml
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'cohesive-qa'
NET='cohesive-qa-isolated'
SOURCE='cohesive-qa-source'
PORTS={'baseline':18161,'candidate':18162}
def docker(*args): return subprocess.check_output(['docker',*args],text=True).strip()
def verify():
    manifest={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('backup/**/*')) if p.is_file()}
    manifest.update({str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('source/*') if p.is_file()})
    hits=[]
    for p in OUT.glob('backup/**/*'):
        if not p.is_file():continue
        text=p.read_text(errors='replace')
        for pattern in [r'-----BEGIN .*PRIVATE KEY',r'(?im)^\s*(?:password|api[-_]?key|token|secret)\s*:\s*[\"\']?[^$\s\"\']+',r'Bearer\s+[A-Za-z0-9._-]{20,}']:
            if re.search(pattern,text):hits.append(str(p.relative_to(OUT)))
    (OUT/'backup-verification.json').write_text(json.dumps({'hashes':manifest,'credential_pattern_hits':hits,'archive_valid':subprocess.run(['tar','-tzf',str(OUT/'deployed-backup.tar.gz')],capture_output=True).returncode==0},indent=2))
    assert not hits,hits
    print('Backup verified:',len(manifest),'files; no credential-pattern hits')
def stage(variant):
    base=OUT/'backup' if variant=='baseline' else ROOT/'tools/dynacat'
    cfg=yaml.safe_load((base/'config/dynacat.yml').read_text())
    cfg['pages']=[p for p in cfg['pages'] if p.get('slug') in ('hardware-workloads','networking')]
    for p in cfg['pages']:
        for c in p['columns']:
            c['widgets']=[w for w in c['widgets'] if w.get('type')!='weather']
            for w in c['widgets']:
                if w.get('url','').startswith('http://workload-summary:8090/'):
                    w['url']=w['url'].replace('http://workload-summary:8090',f'http://{SOURCE}:8090');w['cache']='1s';w['update-interval']='2s'
    cfg['server'].update(port=8080,**{'cache-dir':'/tmp/cache'})
    folder=OUT/variant/'config';folder.mkdir(parents=True,exist_ok=True)
    (folder/'dynacat.yml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    if NET not in docker('network','ls','--format','{{.Name}}').splitlines():docker('network','create','--internal',NET)
    if SOURCE not in docker('ps','-a','--format','{{.Names}}').splitlines():docker('run','-d','--name',SOURCE,'--network',NET,'-v',f'{OUT}/source:/data:ro','-w','/data','python:3.13-slim','python','-m','http.server','8090')
    name='cohesive-qa-'+variant
    if name in docker('ps','-a','--format','{{.Names}}').splitlines():docker('rm','-f',name)
    docker('run','-d','--name',name,'--network',NET,'-p',f'127.0.0.1:{PORTS[variant]}:8080','-v',f'{folder}:/app/config:ro','-v',f'{base}/assets:/app/assets:ro','panonim/dynacat:3.0.0')
    ip=json.loads(docker('inspect',name))[0]['NetworkSettings']['Networks'][NET]['IPAddress']
    url=f'http://{ip}:8080'
    for _ in range(60):
        try:urllib.request.urlopen(url+'/networking',timeout=1);break
        except Exception:time.sleep(.25)
    print('READY',url)
    return url
METRICS='''() => {const rect=e=>{if(!e)return null;let r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}};const all=s=>[...document.querySelectorAll(s)];return {overflow:document.documentElement.scrollWidth>innerWidth,pihole:rect(document.querySelector('.nw-pihole')),infrastructure:rect(document.querySelector('.nw-infrastructure')),gateway:rect(document.querySelector('.nw-gateway')),workloads:rect(document.querySelector('.cw-workloads')),plots:all('.nw-dns-plot').map(e=>({box:rect(e),svg:rect(e.querySelector('svg')),label:e.querySelector('h4')?.textContent,fill:getComputedStyle(e.querySelector('.nw-query-area')).fillOpacity})),rows:all('.cw-workload').map(e=>({box:rect(e),font:getComputedStyle(e).fontSize,link:rect(e.querySelector('a')),summary:rect(e.querySelector('summary'))})),paths:all('.cw-history-line,.cw-history-area,.nw-history path:not(.nw-gridline),.nw-spark path:not(.nw-gridline),.nw-area,.nw-query-line,.nw-query-area').map(e=>({class:e.getAttribute('class'),d:e.getAttribute('d'),fill:getComputedStyle(e).fill,opacity:getComputedStyle(e).fillOpacity})),controls:all('.cw-workloads button,.cw-workloads summary').map(e=>({text:e.textContent.trim(),box:rect(e)}))}}'''
def source_paths(slug):
    data=json.loads((OUT/'source'/('current' if slug=='hardware-workloads' else 'network-current')).read_text())
    histories=[g['history'] for g in data['pve']['guest_inventory'] if g['status']=='running'] if slug=='hardware-workloads' else [d['history'] for d in data['devices']]+[data['pihole']['query_history']]
    result=[]
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('path','area_path') and isinstance(v,str):result.append(v)
                elif isinstance(v,(list,dict)):walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(histories)
    return Counter(result)
def interactions(page,context,slug,width):
    result={};source=OUT/'source'/('current' if slug=='hardware-workloads' else 'network-current');original=source.read_bytes();data=json.loads(original)
    try:
        if slug=='hardware-workloads':
            summaries=page.locator('.cw-docker summary');summary=summaries.nth(1)
            summary.evaluate('e=>e.parentElement.open=false');summary.focus();page.keyboard.press('Enter')
            result['keyboard_expand']=summary.evaluate('e=>e.parentElement.open')
            result['single_header_control']=page.locator('[data-cw-collapse-all]').count()==1
            result['no_redundant_controls']=page.locator('[data-cw-collapse]').count()==0
            button=page.locator('[data-cw-collapse-all]');button.focus();page.keyboard.press('Enter')
            result['collapse_all']=page.locator('.cw-docker[open]').count()==0
            summary.focus();page.keyboard.press('Enter');result['reexpand']=summary.evaluate('e=>e.parentElement.open')
            data['running_containers']+=1;marker=f"{data['running_containers']}/{data['containers_total']}"
        else:
            data['pihole']['total_queries']+=1;marker=str(data['pihole']['total_queries'])
        # Explicitly labelled refresh-only mutation; screenshots always precede it.
        source.write_text(json.dumps(data))
        page.wait_for_function('(text)=>document.body.textContent.includes(text)',arg=marker,timeout=15000)
        result['actual_changed_native_refresh']=True
        if slug=='hardware-workloads':
            result['expanded_state_after_refresh']=page.locator('.cw-docker').nth(1).evaluate('e=>e.open')
            result['summary_touch_target']=all(x['height']>=44 for x in page.locator('.cw-docker summary').evaluate_all('es=>es.map(e=>({height:e.getBoundingClientRect().height}))'))
        if width==390:
            page.evaluate('document.activeElement?.blur()')
            session=context.new_cdp_session(page)
            for typ,pts in [('touchStart',[{'x':195,'y':900}]),('touchMove',[{'x':195,'y':350}]),('touchEnd',[])]:session.send('Input.dispatchTouchEvent',{'type':typ,'touchPoints':pts})
            page.wait_for_timeout(1500);before=page.evaluate('scrollY')
            source.write_bytes(original)
            page.wait_for_timeout(5500)
            result['touch_refresh_drift']=page.evaluate('scrollY')-before
            result['touch_scroll_stable']=abs(result['touch_refresh_drift'])<2
    except Exception as e:result['error']=str(e)
    finally:source.write_bytes(original)
    return result

def live_interactions(page,context,slug,width):
    """Observe real production polls only; never replace responses or alter sources."""
    result={}
    selector='.cw-workloads' if slug=='hardware-workloads' else '.nw-dashboard'
    if slug=='hardware-workloads':
        summary=page.locator('.cw-docker summary').nth(1)
        summary.evaluate('e=>e.parentElement.open=false');summary.focus();page.keyboard.press('Enter')
        result['keyboard_expand']=summary.evaluate('e=>e.parentElement.open')
        page.locator('[data-cw-collapse-all]').focus();page.keyboard.press('Enter')
        result['collapse_all']=page.locator('.cw-docker[open]').count()==0
        summary.focus();page.keyboard.press('Enter')
        result['summary_touch_target']=page.locator('.cw-docker summary').evaluate_all('es=>es.every(e=>e.getBoundingClientRect().height>=44)')
        result['link_touch_targets']=page.locator('.cw-workload>.k-host').evaluate_all('es=>es.every(e=>e.getBoundingClientRect().height>=44 && e.href && e.title)')
    page.evaluate('document.activeElement?.blur()')
    if width==390:
        session=context.new_cdp_session(page)
        session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':195,'y':900}]})
        for y in range(850,349,-50):
            session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':195,'y':y}]})
            page.wait_for_timeout(70)
        # Release without fling: momentum is user scrolling, not refresh drift.
        page.wait_for_timeout(250)
        session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        page.wait_for_timeout(1500)
        samples=[]
        for _ in range(8):
            samples.append(page.evaluate('scrollY'));page.wait_for_timeout(250)
        assert len(set(samples[-4:]))==1,('Touch scroll not settled',samples)
    before=page.evaluate('scrollY')
    original=page.locator(selector).inner_text()
    page.wait_for_function('(a)=>document.querySelector(a.selector)?.innerText!==a.original',arg={'selector':selector,'original':original},timeout=45000)
    result['actual_changed_live_refresh']=True
    if slug=='hardware-workloads':result['expanded_state_after_refresh']=page.locator('.cw-docker').nth(1).evaluate('e=>e.open')
    if width==390:
        result['touch_refresh_drift']=page.evaluate('scrollY')-before
        result['touch_scroll_stable']=abs(result['touch_refresh_drift'])<2
    return result

def capture(variant,url):
    reports=[]
    with sync_playwright() as p:
        b=p.chromium.launch()
        for slug in ('hardware-workloads','networking'):
            for width in (1600,390):
                for theme,key in [('dark','midnight-navy'),('light','catppuccin-latte')]:
                    c=b.new_context(viewport={'width':width,'height':1100},is_mobile=width==390,has_touch=width==390,color_scheme=theme)
                    c.add_init_script("HTMLMediaElement.prototype.play=()=>Promise.reject(new Error('QA blocks audio'));window.__audioBlocked=true")
                    c.route('**/*',lambda route: route.continue_() if route.request.url.startswith(url+'/') and route.request.resource_type!='media' else route.abort())
                    page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(url+'/'+slug);page.locator('.nw-pihole' if slug=='networking' else '.cw-workloads').wait_for(timeout=30000)
                    page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()');page.wait_for_timeout(500)
                    stem=f'{variant}-{slug}-{theme}-{width}'
                    page.screenshot(path=str(OUT/(stem+'-page.png')),full_page=True)
                    page.locator('.nw-pihole' if slug=='networking' else '.cw-workloads').screenshot(path=str(OUT/(stem+'-widget.png')))
                    m=page.evaluate(METRICS);m.update(slug=slug,width=width,theme=theme,errors=errors)
                    checks={'no_overflow':not m['overflow'],'no_js_errors':not errors}
                    if variant!='live':
                        selector='.cw-workloads svg path:not(.cw-history-grid)' if slug=='hardware-workloads' else '.network-widget svg path:not(.nw-gridline)'
                        if slug=='networking':selector='.nw-dashboard svg path:not(.nw-gridline)'
                        rendered=Counter(page.locator(selector).evaluate_all("es=>es.map(e=>e.getAttribute('d'))"))
                        expected=source_paths(slug)
                        # Pi-hole response also includes permitted series, deliberately not rendered.
                        if slug=='networking':
                            source=json.loads((OUT/'source/network-current').read_text())
                            h=source['pihole']['query_history'].get('permitted',{})
                            for k in ('path','area_path'):
                                if k in h:expected[h[k]]-=1
                            expected=+expected
                        checks['exact_source_line_and_area_paths']=rendered==expected
                        m['path_counts']={'rendered':sum(rendered.values()),'expected':sum(expected.values()),'missing':sum((expected-rendered).values()),'extra':sum((rendered-expected).values())}
                    if slug=='networking':
                        a=m['pihole'];g=m['gateway']
                        checks.update(two_distinct_plots=len(m['plots'])==2,plot_height=all(70<=x['svg']['height']<=110 for x in m['plots']),shading=all(float(x['fill'])>=.35 for x in m['plots']))
                        if width==1600:checks.update(pihole_left_gateway_right=bool(g and a['x']<g['x'] and abs(a['y']-g['y'])<=20),equal_halves=bool(g and abs(a['width']-g['width'])<=20 and .42*width<=a['width']<=.51*width),matching_top_card_heights=bool(g and abs(a['height']-g['height'])<=20))
                    else:
                        checks.update(readable_rows=all(float(x['font'].replace('px',''))>=12 for x in m['rows']),compact_rows=all(x['box']['height']<=72 if width==1600 else x['box']['height']<=150 for x in m['rows']),shaded_history=any('area' in x['class'] and x['d'] for x in m['paths']))
                    if slug=='networking' and width==390:
                        checks['mobile_stack']=g['y']>=a['y']+a['height'] and abs(g['width']-a['width'])<1
                    m['checks']=checks
                    if variant=='candidate':m['interactions']=interactions(page,c,slug,width)
                    if variant=='live':m['interactions']=live_interactions(page,c,slug,width)
                    reports.append(m);c.close()
        b.close()
    (OUT/f'{variant}-report.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps([{'slug':m['slug'],'width':m['width'],'theme':m['theme'],'checks':m['checks']} for m in reports],indent=2))
    if variant in ('candidate','live'):
        failures=[f"{m['slug']}/{m['theme']}/{m['width']}: {k}" for m in reports for k,v in {**m['checks'],**m.get('interactions',{})}.items() if v is False or k=='error']
        assert not failures,'Acceptance failures: '+ '; '.join(failures)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['live','baseline','candidate','verify','stage-candidate']);args=ap.parse_args();OUT.mkdir(exist_ok=True)
    if args.mode=='verify':verify()
    elif args.mode=='stage-candidate':stage('candidate')
    else:capture(args.mode,'http://192.168.2.72:8080' if args.mode=='live' else stage(args.mode))
