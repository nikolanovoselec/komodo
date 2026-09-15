"""Read-only real Plex QA. Credentials loaded in memory; no remote modifications."""
import os, sys, json, threading, subprocess, urllib.request, urllib.parse, pathlib, time, re
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'adapter'))
import radio
OUT=pathlib.Path('/srv/hermes/workspaces/radio-qa'); OUT.mkdir(exist_ok=True)
LIVE='http://192.168.2.72:8080'

def setup():
    p=subprocess.run(['ssh','-i','/root/.ssh/hermes-network','-o','BatchMode=yes','root@192.168.2.72','docker','exec','tools_dynacat_workload_summary','python3','-c',"'import os;print(os.environ[\"DYNACAT_PLEX_TOKEN\"])'"],capture_output=True,check=True)
    os.environ['DYNACAT_PLEX_TOKEN']=p.stdout.decode().strip()
    assert os.environ['DYNACAT_PLEX_TOKEN']
    class Stage(radio.Handler):
        def do_GET(self):
            if self.path.startswith('/radio/'):
                return super().do_GET()
            path=urllib.parse.urlsplit(self.path).path
            if path.startswith('/assets/') and (ROOT/path.lstrip('/')).is_file():
                body=(ROOT/path.lstrip('/')).read_bytes()
                mime='text/javascript' if path.endswith('.js') else 'text/css'
            else:
                try:
                    with urllib.request.urlopen(urllib.request.Request(LIVE+self.path,headers={'Cookie': self.headers.get('Cookie','')}),timeout=20) as r:
                        body=r.read(); mime=r.headers.get('Content-Type','application/octet-stream')
                    if path.endswith('/js/page.js'):
                        # Exercise the exact tracked nginx substitution, not a QA-only implementation.
                        rule=re.search(r"sub_filter 'setupPage\(\)\.then\(\(\) => \{' '([^']+)';",(ROOT/'gateway.conf').read_text()).group(1)
                        assert body.count(b'setupPage().then(() => {')==1
                        body=body.replace(b'setupPage().then(() => {',rule.encode())
                except Exception:
                    self.send_error(502);return
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        do_HEAD=radio.Handler.do_HEAD
    s=radio.make_server(('127.0.0.1',0));s.RequestHandlerClass=Stage
    threading.Thread(target=s.serve_forever,daemon=True).start()
    return s,'http://127.0.0.1:'+str(s.server_port)

def main():
    s,url=(None,LIVE) if os.environ.get('QA_DEPLOYED')=='1' else setup(); result={'staging':url,'queue_normalization_workaround':os.environ.get('QA_NORMALIZE_QUEUE')=='1','checks':{},'errors':[]}
    def record(k,v):
        result['checks'][k]=v;print(k,json.dumps(v));(OUT/'results.json').write_text(json.dumps(result,indent=2))
    with urllib.request.urlopen(url+'/radio/queue',timeout=120) as r: q=json.load(r)
    record('real_queue',{'count':len(q['tracks']),'codecs':sorted(set(t['codec'] for t in q['tracks']))})
    assert q['tracks']
    stream=url+q['tracks'][0]['stream']
    for name,method,headers in [('head','HEAD',{}),('range','GET',{'Range':'bytes=0-4095'}),('full_get','GET',{})]:
        with urllib.request.urlopen(urllib.request.Request(stream,method=method,headers=headers),timeout=20) as r:
            b=r.read();record(name,{'status':r.status,'type':r.headers.get('Content-Type'),'length':r.headers.get('Content-Length'),'range':r.headers.get('Content-Range'),'bytes':len(b)})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        child=None; profile=None
        if os.environ.get('QA_REAL_BACKGROUND')=='1':
            # Playwright normally forces every page to be visible through focus
            # emulation. A fresh owned browser + no_defaults proves actual hidden
            # tab playback, not just bring_to_front on an always-visible page.
            import tempfile
            profile=tempfile.TemporaryDirectory(prefix='construct-radio-qa-')
            child=subprocess.Popen([pw.chromium.executable_path,'--no-sandbox','--mute-audio','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile.name,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            import atexit
            atexit.register(child.terminate)
            port_file=pathlib.Path(profile.name)/'DevToolsActivePort'
            deadline=time.monotonic()+20
            while not port_file.exists():
                if time.monotonic()>deadline: child.terminate();raise RuntimeError('Owned QA browser did not start')
                time.sleep(.1)
            browser=pw.chromium.connect_over_cdp('http://127.0.0.1:'+port_file.read_text().splitlines()[0],no_defaults=True)
            ctx=browser.contexts[0]
        else:
            browser=pw.chromium.launch(headless=os.environ.get('QA_HEADFUL')!='1',args=['--mute-audio'])
            ctx=browser.new_context(viewport={'width':1440,'height':1100})
        ctx.add_init_script("""(() => {
          window.__qaNative={sse:0,overlaps:0,updates:0};const active=new Map(),original=window.fetch;
          window.fetch=async function(url,...args){const key=String(url),widget=key.includes('/api/widgets/');
            if(widget){const n=(active.get(key)||0)+1;active.set(key,n);if(n>1)window.__qaNative.overlaps++;}
            try{return await original.call(this,url,...args);}finally{if(widget)active.set(key,active.get(key)-1);}
          };
          const NativeSource=window.EventSource;window.EventSource=class extends NativeSource {constructor(...args){super(...args);window.__qaNative.sse++;}};
          document.addEventListener('dynacat:widget-updated',e=>{if(e.detail?.widget)window.__qaNative.updates++;});
        })();""")
        page=ctx.new_page();page.set_viewport_size({'width':1440,'height':1100});page.on('pageerror',lambda e: result['errors'].append(str(e)))
        def wait_expression(expression,timeout=30000,arg=None):
            deadline=time.monotonic()+timeout/1000
            while time.monotonic()<deadline:
                if page.evaluate(expression,arg): return
                page.wait_for_timeout(100)
            raise AssertionError('Timed out waiting for browser state')
        # Poll via CDP evaluation; Playwright string predicates use eval blocked by CSP.
        page.wait_for_function=wait_expression
        requests=[];page.on('request',lambda r: requests.append(r.url) if '/radio/' in r.url else None)
        page.goto(url+'/media',wait_until='networkidle');page.locator('#plex-radio').wait_for()
        page.evaluate("document.querySelector('#plex-radio-audio').muted=true")
        snap="""() => {let a=document.querySelector('#plex-radio-audio'); return {paused:a.paused,muted:a.muted,time:a.currentTime,duration:Number.isFinite(a.duration)?a.duration:null,ready:a.readyState,decoded:a.webkitAudioDecodedByteCount||0,src:a.getAttribute('src'),error:a.error?.code||null}}"""
        record('no_autoplay',{'audio':page.evaluate(snap),'radio_requests':len(requests)})
        page.get_by_role('button',name='Play',exact=True).click()
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>1",timeout=120000)
        start=page.evaluate(snap);page.wait_for_timeout(1600);finish=page.evaluate(snap)
        record('real_muted_playback',{'start':start,'end':finish,'advances':finish['time']>start['time'],'decoded':finish['decoded']>0})
        page.get_by_role('button',name='Pause',exact=True).click();before=page.evaluate(snap);page.wait_for_timeout(700)
        record('pause',{'before':before,'after':page.evaluate(snap)})
        first=before['src'];page.get_by_role('button',name='Next track').click();next_src=page.evaluate(snap)['src'];page.get_by_role('button',name='Previous track').click()
        record('next_previous',{'changed':first!=next_src,'restored':page.evaluate(snap)['src']==first,'remains_paused':page.evaluate(snap)['paused']})
        shuffle=page.get_by_role('button',name='Shuffle',exact=True);old=page.evaluate(snap)['src'];shuffle.click()
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>0.5")
        record('shuffle',{'different':old!=page.evaluate(snap)['src'],'playing':not page.evaluate(snap)['paused'],'not_toggle':shuffle.get_attribute('aria-pressed') is None})
        record('seek_volume_controls',{'ranges':page.locator('#plex-radio input[type=range]').count(),'native_controls':page.locator('#plex-radio-audio[controls]').count()})
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>0.5")
        page.get_by_role('slider',name='Seek',exact=True).fill('45');page.get_by_role('slider',name='Seek',exact=True).dispatch_event('change')
        page.get_by_role('slider',name='Volume',exact=True).fill('27');page.get_by_role('slider',name='Volume',exact=True).dispatch_event('input')
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>45.5 && document.querySelector('#plex-radio-audio').readyState>=2")
        record('seek_volume_UI',{'audio':page.evaluate(snap),'volume':page.locator('#plex-radio-audio').evaluate('(a)=>a.volume')})
        page.evaluate("window.__qaAudio=document.querySelector('#plex-radio-audio');document.dispatchEvent(new Event('dynacat:widget-updated'))")
        record('widget_refresh',{'same_audio':page.evaluate("window.__qaAudio===document.querySelector('#plex-radio-audio')"),'audio':page.evaluate(snap)})
        for width,label in [(1440,'desktop'),(390,'mobile390')]:
            page.set_viewport_size({'width':width,'height':1100})
            for theme in ['dark','light']:
                key='default' if theme=='dark' else 'default-light'
                page.locator('.theme-choices [data-key="'+key+'"]').first.evaluate('(el)=>el.click()')
                page.wait_for_function('(key)=>document.documentElement.dataset.theme===key',arg=key)
                page.wait_for_timeout(250)
                page.locator('#plex-radio').screenshot(path=str(OUT/f'{label}-{theme}.png'))
                page.screenshot(path=str(OUT/f'{label}-{theme}-page.png'),full_page=True)
                record(label+'_'+theme,{'horizontal_overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')})
        page.set_viewport_size({'width':1440,'height':1100})
        route_checks={}
        for route in ['hardware-workloads','endpoints-services','media','hardware-workloads']:
            before=page.evaluate(snap)
            page.locator('nav.nav a[href="/'+route+'"]').click()
            page.wait_for_function('(route)=>location.pathname==="/"+route',arg=route)
            page.wait_for_timeout(1200)
            after=page.evaluate(snap)
            route_checks[route]=page.evaluate("window.__qaAudio===document.querySelector('#plex-radio-audio')") and before['src']==after['src'] and after['time']>before['time'] and not after['paused']
        # Browser back and the mobile dropdown must use the same persistent path.
        page.go_back();page.wait_for_function("location.pathname==='/media'")
        page.set_viewport_size({'width':390,'height':1100})
        page.get_by_role('combobox',name='Navigate pages').select_option('/endpoints-services')
        page.wait_for_function("location.pathname==='/endpoints-services'")
        route_checks['mobile_back']=page.evaluate("window.__qaAudio===document.querySelector('#plex-radio-audio') && !window.__qaAudio.paused")
        record('internal_navigation',route_checks)
        record('mini_layout',page.locator('#plex-radio').evaluate('(el)=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth}}'))
        page.screenshot(path=str(OUT/'mobile-mini-player.png'),full_page=True)
        # The owned Chromium process is muted with --mute-audio. Leave the
        # element unmuted here: Chromium suspends inaudible *element-muted*
        # media in hidden tabs, which would not represent normal radio use.
        page.evaluate("document.querySelector('#plex-radio-audio').muted=false")
        before=page.evaluate(snap);other=ctx.new_page();other.goto('about:blank');other.bring_to_front();other.wait_for_timeout(2200)
        after=page.evaluate(snap)
        record('background_tab',{'advances':after['time']>before['time']+1,'decoded_advances':after['decoded']>before['decoded'],'playing':not after['paused'],'same_source':after['src']==before['src'],'start':before['time'],'end':after['time'],'visibility':page.evaluate('document.visibilityState')})
        other.close();page.bring_to_front()
        first=page.evaluate(snap)['src'];page.get_by_role('button',name='Next track').click()
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>0.5")
        changed=page.evaluate(snap)['src']!=first
        page.get_by_role('button',name='Previous track').click()
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>0.5")
        restored=page.evaluate(snap)['src']==first
        page.get_by_role('button',name='Pause',exact=True).click();paused=page.evaluate(snap)['paused']
        page.get_by_role('button',name='Shuffle',exact=True).click()
        page.wait_for_function("document.querySelector('#plex-radio-audio').currentTime>0.5")
        after=page.evaluate(snap)
        record('post_navigation_controls',{'next':changed,'previous':restored,'pause':paused,'shuffle':after['src']!=first and not after['paused'],'decoded':after['decoded']>0})
        search=page.locator('#endpoint-search');search.fill('no-such-endpoint-radio-qa')
        record('endpoint_filter_after_navigation',page.locator('.es-empty').is_visible());search.fill('')
        page.get_by_role('combobox',name='Navigate pages').select_option('/hardware-workloads')
        page.wait_for_function("location.pathname==='/hardware-workloads'")
        page.set_viewport_size({'width':1440,'height':1100})
        calendar=page.locator('[data-calendar-title]');before=calendar.inner_text()
        page.locator('[data-calendar-action=next]').click()
        record('calendar_after_navigation',before!=calendar.inner_text())
        page.locator('.theme-choices [data-key="default"]').first.evaluate('(el)=>el.click()')
        page.wait_for_function("document.documentElement.dataset.theme==='default'")
        record('theme_after_navigation',page.evaluate("document.documentElement.dataset.theme==='default'"))
        record('native_lifecycle',page.evaluate('window.__qaNative'))
        record('transport_targets',page.locator('#plex-radio [data-action=next]').evaluate('(el)=>({glyph:getComputedStyle(el).fontSize,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height})'))
        page.goto(url+'/media',wait_until='networkidle');record('fresh_page_no_autoplay',page.evaluate(snap))
        record('poster',page.locator('#plex-radio img').count())
        browser.close()
        if child is not None: child.terminate();child.wait(timeout=10)
        if profile is not None: profile.cleanup()
    c=result['checks']
    assert c['head']['status']==200 and c['head']['bytes']==0
    assert c['range']['status']==206 and c['range']['bytes']==4096
    assert c['full_get']['bytes']==int(c['full_get']['length'])
    assert c['real_muted_playback']['advances'] and c['real_muted_playback']['decoded']
    assert c['pause']['before']['time']==c['pause']['after']['time']
    assert all(c['next_previous'].values())
    assert all(c['shuffle'].values())
    assert c['seek_volume_UI']['volume']==0.27
    assert c['widget_refresh']['same_audio']
    assert all(c['internal_navigation'].values())
    assert all(c['background_tab'][key] for key in ['advances','decoded_advances','playing','same_source'])
    assert c['mini_layout']['left']>=0 and c['mini_layout']['right']<=c['mini_layout']['width'] and not c['mini_layout']['overflow']
    if os.environ.get('QA_REAL_BACKGROUND')=='1': assert c['background_tab']['visibility']=='hidden'
    assert all(c['post_navigation_controls'].values())
    assert c['native_lifecycle']['sse']==1 and c['native_lifecycle']['overlaps']==0 and c['native_lifecycle']['updates']>0
    assert c['endpoint_filter_after_navigation'] and c['calendar_after_navigation'] and c['theme_after_navigation']
    assert c['transport_targets']['glyph']=='24px' and c['transport_targets']['width']>=44 and c['transport_targets']['height']>=44
    assert c['no_autoplay']['radio_requests']==0 and c['no_autoplay']['audio']['paused']
    assert c['fresh_page_no_autoplay']['paused'] and c['fresh_page_no_autoplay']['src'] is None
    assert not result['errors']
    (OUT/'results.json').write_text(json.dumps(result,indent=2));s.shutdown() if s else None

if __name__=='__main__':main()
