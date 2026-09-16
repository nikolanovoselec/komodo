"""Native live-shell radio QA with isolated, inert media and blocked streams.
Use URL OUTPUT [--candidate]; candidate routes only the scoped local radio asset.
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent
STUB = """(() => {
window.__plays=0;window.__pauses=0;window.__sse=[];
Object.defineProperty(HTMLMediaElement.prototype,'src',{configurable:true,get(){return this.__src||''},set(v){this.__src=v}});
Object.defineProperty(HTMLMediaElement.prototype,'paused',{configurable:true,get(){return this.__paused!==false}});
Object.defineProperty(HTMLMediaElement.prototype,'ended',{configurable:true,get(){return !!this.__ended}});
HTMLMediaElement.prototype.play=function(){window.__plays++;this.__paused=false;return new Promise((ok,no)=>{window.__playOK=ok;window.__playNO=no})};
HTMLMediaElement.prototype.pause=function(){window.__pauses++;this.__paused=true;this.dispatchEvent(new Event('pause'))};
HTMLMediaElement.prototype.load=function(){};
window.EventSource=class extends EventTarget {static CLOSED=2; constructor(){super();window.__sse.push(this)} close(){}};
window.__event=(name)=>{const a=document.querySelector('#plex-radio-audio');if(name==='playing'){a.__paused=false;a.__ended=false}if(name==='ended')a.__ended=true;a.dispatchEvent(new Event(name))};
})();"""

def main():
    url, output = sys.argv[1:3]
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as p:
        for engine in ('chromium', 'webkit'):
            browser = getattr(p, engine).launch()
            for width in (1440, 390):
                for theme in ('midnight-navy', 'catppuccin-latte'):
                    context = browser.new_context(bypass_csp=True, viewport={'width': width, 'height': 900}, is_mobile=width<600, has_touch=width<600)
                    context.add_init_script(STUB)
                    page = context.new_page(); streams = []; errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    def block(route):
                        streams.append(route.request.url); route.abort()
                    page.route('**/radio/stream/**', block)
                    page.route('**/radio/queue', lambda r: r.fulfill(json={'tracks':[{'id':'1','stream':'/radio/stream/1','title':'QA only'},{'id':'2','stream':'/radio/stream/2','title':'QA second'}]}))
                    if '--candidate' in sys.argv:
                        page.route('**/assets/plex-radio.js*', lambda r: r.fulfill(path=str(ROOT/'assets/plex-radio.js'),content_type='text/javascript'))
                    page.goto(url+'/networking'); page.wait_for_function('typeof window.constructNavigate === "function"')
                    assert page.locator('#plex-radio:visible').count()==0
                    def nav(path):
                        if width<600: page.locator('.cc-page-select').select_option(path)
                        else: page.locator(f'.header-container .nav-item[href="{path}"]').click()
                        page.wait_for_url('**'+path); page.wait_for_timeout(250)
                    nav('/media'); card=page.locator('#plex-radio'); card.wait_for()
                    page.locator(f'.theme-choices [data-key="{theme}"]').first.evaluate('e=>e.click()')
                    page.evaluate('window.__audio=document.querySelector("#plex-radio-audio")')
                    assert page.evaluate('window.__plays===0 && !window.__audio.src')
                    assert card.locator('.pr-title').inner_text()
                    nav('/hardware-workloads'); assert card.is_hidden()
                    nav('/networking'); assert card.is_hidden()
                    # Exercise actual native poll and SSE morph paths with changed captured markup.
                    widget=page.locator('.widget[data-widget-id]').first
                    wid=widget.get_attribute('data-widget-id')
                    fragment=page.request.get(url+f'/api/widgets/{wid}/content/').text()
                    for cycle in range(3):
                        html=fragment.replace('</div>',f'<span data-radio-qa="{cycle}"></span></div>',1)
                        page.route(f'**/api/widgets/{wid}/content/*',lambda r:r.fulfill(body=html,content_type='text/html'))
                        page.evaluate('(id)=>window.dynacatRefreshWidget(id)',wid)
                        assert page.locator(f'[data-radio-qa="{cycle}"]').count()>0
                        assert card.is_hidden()
                        assert page.evaluate('window.__sse.length')>0
                        page.evaluate('([widgetId,html])=>{for(const s of window.__sse)s.dispatchEvent(new MessageEvent("widget-update",{data:JSON.stringify({widgetId,html})}))}',[wid,html.replace('data-radio-qa','data-radio-sse')])
                        assert card.is_hidden()
                    nav('/media'); assert card.is_visible()
                    card.locator('[data-action="play"]').click(); page.wait_for_function('() => window.__plays===1')
                    nav('/networking'); assert card.is_hidden()
                    page.evaluate('window.__playOK()'); page.wait_for_timeout(50); assert card.is_hidden()
                    page.evaluate('__event("playing")'); assert card.is_visible()
                    assert card.evaluate('e=>getComputedStyle(e).display')!='none'
                    page.evaluate('__event("waiting")'); assert card.is_visible()
                    nav('/endpoints-services'); assert card.is_visible()
                    page.evaluate('window.__audio.pause()'); assert card.is_hidden()
                    page.evaluate('__event("playing")'); assert card.is_visible()
                    before=page.evaluate('window.__pauses')
                    card.locator('[data-action="dismiss"]').click(); assert card.is_hidden()
                    page.evaluate('__event("playing")'); assert card.is_hidden()
                    nav('/networking'); assert card.is_hidden()
                    assert page.evaluate('window.__pauses')==before
                    nav('/media'); assert card.is_visible()
                    nav('/networking'); assert card.is_visible()
                    page.evaluate('__event("ended")'); assert card.is_hidden()
                    page.evaluate('__event("error")'); assert card.is_hidden()
                    nav('/media'); assert card.is_visible()
                    page.evaluate('window.__audio.pause()')
                    nav('/networking'); assert card.is_hidden()
                    page.go_back(); page.wait_for_url('**/media'); assert card.is_visible()
                    assert page.evaluate('window.__audio===document.querySelector("#plex-radio-audio")')
                    assert not streams, streams
                    assert not errors, errors
                    rows.append({'engine':engine,'width':width,'theme':theme,'native_poll_cycles':3,'sse_cycles':3,'streams':len(streams),'audio_identity':True,'lifecycle_and_real_navigation':True})
                    context.close()
            browser.close()
    (out/'report.json').write_text(json.dumps(rows,indent=2)); print(json.dumps(rows,indent=2))
if __name__=='__main__': main()
