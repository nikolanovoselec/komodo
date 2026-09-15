"""Read-only real Plex QA. Credentials loaded in memory; no remote modifications."""
import os, sys, json, threading, subprocess, urllib.request, pathlib, time
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
            if self.path in ['/assets/plex-radio.js','/assets/plex-radio.css']:
                body=(ROOT/self.path.lstrip('/')).read_bytes()
                mime='text/javascript' if self.path.endswith('.js') else 'text/css'
            else:
                try:
                    with urllib.request.urlopen(urllib.request.Request(LIVE+self.path,headers={'Cookie': self.headers.get('Cookie','')}),timeout=20) as r:
                        body=r.read(); mime=r.headers.get('Content-Type','application/octet-stream')
                    if 'text/html' in mime:
                        body=body.replace(b'</head>',b'<link rel="stylesheet" href="/assets/plex-radio.css"><script defer src="/assets/plex-radio.js"></script></head>')
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
        browser=pw.chromium.launch(headless=True,args=['--mute-audio'])
        ctx=browser.new_context(viewport={'width':1440,'height':1100})
        page=ctx.new_page();page.on('pageerror',lambda e: result['errors'].append(str(e)))
        requests=[];page.on('request',lambda r: requests.append(r.url) if '/radio/' in r.url else None)
        page.goto(url+'/media',wait_until='networkidle');page.locator('#plex-radio').wait_for()
        page.evaluate("document.querySelector('#plex-radio audio').muted=true")
        snap="""() => {let a=document.querySelector('#plex-radio audio'); return {paused:a.paused,muted:a.muted,time:a.currentTime,duration:Number.isFinite(a.duration)?a.duration:null,ready:a.readyState,decoded:a.webkitAudioDecodedByteCount||0,src:a.getAttribute('src'),error:a.error?.code||null}}"""
        record('no_autoplay',{'audio':page.evaluate(snap),'radio_requests':len(requests)})
        page.get_by_role('button',name='Play',exact=True).click()
        page.wait_for_function("document.querySelector('#plex-radio audio').currentTime>1",timeout=120000)
        start=page.evaluate(snap);page.wait_for_timeout(1600);finish=page.evaluate(snap)
        record('real_muted_playback',{'start':start,'end':finish,'advances':finish['time']>start['time'],'decoded':finish['decoded']>0})
        page.get_by_role('button',name='Pause',exact=True).click();before=page.evaluate(snap);page.wait_for_timeout(700)
        record('pause',{'before':before,'after':page.evaluate(snap)})
        first=before['src'];page.get_by_role('button',name='Next track').click();next_src=page.evaluate(snap)['src'];page.get_by_role('button',name='Previous track').click()
        record('next_previous',{'changed':first!=next_src,'restored':page.evaluate(snap)['src']==first,'remains_paused':page.evaluate(snap)['paused']})
        shuffle=page.get_by_role('button',name='Shuffle',exact=True);old=shuffle.get_attribute('aria-pressed');shuffle.click();record('shuffle',{'before':old,'after':shuffle.get_attribute('aria-pressed')})
        record('seek_volume_controls',{'ranges':page.locator('#plex-radio input[type=range]').count(),'native_controls':page.locator('#plex-radio audio[controls]').count()})
        page.get_by_role('button',name='Play',exact=True).click()
        page.wait_for_function("document.querySelector('#plex-radio audio').currentTime>0.5")
        page.get_by_role('slider',name='Seek',exact=True).fill('45');page.get_by_role('slider',name='Seek',exact=True).dispatch_event('change')
        page.get_by_role('slider',name='Volume',exact=True).fill('27');page.get_by_role('slider',name='Volume',exact=True).dispatch_event('input')
        page.wait_for_function("document.querySelector('#plex-radio audio').currentTime>45.5 && document.querySelector('#plex-radio audio').readyState>=2")
        record('seek_volume_UI',{'audio':page.evaluate(snap),'volume':page.locator('#plex-radio audio').evaluate('(a)=>a.volume')})
        page.evaluate("window.__qaAudio=document.querySelector('#plex-radio audio');document.dispatchEvent(new Event('dynacat:widget-updated'))")
        record('widget_refresh',{'same_audio':page.evaluate("window.__qaAudio===document.querySelector('#plex-radio audio')"),'audio':page.evaluate(snap)})
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
        page.evaluate("history.pushState({},'', '/home')")
        record('navigate_away',page.evaluate("({card:!!document.querySelector('#plex-radio'),paused:window.__qaAudio.paused,src:window.__qaAudio.getAttribute('src')})"))
        page.goto(url+'/media',wait_until='networkidle');record('fresh_page_no_autoplay',page.evaluate(snap))
        record('poster',page.locator('#plex-radio img').count())
        browser.close()
    c=result['checks']
    assert c['head']['status']==200 and c['head']['bytes']==0
    assert c['range']['status']==206 and c['range']['bytes']==4096
    assert c['full_get']['bytes']==int(c['full_get']['length'])
    assert c['real_muted_playback']['advances'] and c['real_muted_playback']['decoded']
    assert c['pause']['before']['time']==c['pause']['after']['time']
    assert all(c['next_previous'].values())
    assert c['shuffle']['before']!=c['shuffle']['after']
    assert c['seek_volume_UI']['volume']==0.27
    assert c['widget_refresh']['same_audio']
    assert c['navigate_away']=={'card':False,'paused':True,'src':None}
    assert c['fresh_page_no_autoplay']['paused'] and c['fresh_page_no_autoplay']['src'] is None
    assert not result['errors']
    (OUT/'results.json').write_text(json.dumps(result,indent=2));s.shutdown() if s else None

if __name__=='__main__':main()
