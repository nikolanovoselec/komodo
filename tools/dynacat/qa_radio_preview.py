"""Isolated actual Dynacat SSR + enhancement QA; never requests Plex audio.
Run with QA venv: qa_radio_preview.py CAPTURED_PREVIEW_JSON EVIDENCE_DIR
Capture is explicitly read-only real /radio/queue metadata projected to {track,error}.
Only the radio widget is staged. Controls use a stub play(), not real audio.
"""

import html
import http.server
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import yaml
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent

def main():
    capture, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    state = json.loads(capture.read_text())
    track = state['track']
    state['poster_base64'] = track['poster'].removeprefix('data:image/jpeg;base64,')
    config = yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
    widget = next(w for p in config['pages'] for c in p['columns'] for w in c['widgets'] if w.get('css-class') == 'plex-radio-widget')
    requests = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            data = json.dumps(state).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, format, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 18091), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    widget['url'] = 'http://127.0.0.1:18091/preview'
    widget['cache'] = '1s'
    widget['update-interval'] = '1s'
    stage = {'server': {'port':18090}, 'theme': {'background-color':'225 14 8', 'primary-color':'158 60 52', 'custom-css-file':'/assets/plex-radio.css'}, 'pages':[{'name':'Media · STAGED captured metadata', 'slug':'media', 'columns':[{'size':'full','widgets':[widget]}]}]}
    (out/'dynacat.yml').write_text(yaml.safe_dump(stage, sort_keys=False))
    name = 'radio-preview-stage'
    subprocess.run(['docker','run','-d','--name',name,'--network','host','-v',str(out.resolve()/'dynacat.yml')+':/app/config/dynacat.yml:ro','-v',str(ROOT.resolve()/'assets')+':/app/assets:ro','panonim/dynacat:3.0.0'],check=True,capture_output=True)
    base = 'http://127.0.0.1:18090'
    report = {'source':'Captured real metadata; local native renderer; no Plex playback', 'track':{k:track[k] for k in ['id','title','artist','album']}, 'screens':[]}
    try:
        for _ in range(40):
            try:
                initial = urllib.request.urlopen(base+'/api/pages/media/content/', timeout=2).read().decode()
                break
            except (OSError, TimeoutError):
                time.sleep(.25)
        else:
            raise RuntimeError('Local native renderer did not become ready')
        (out/'initial-server.html').write_text(initial)
        assert html.escape(track['title']) in initial
        assert 'src="data:image/jpeg;base64,' in initial and '#ZgotmplZ' not in initial
        assert '<audio' not in initial
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--no-sandbox'])
            for label, width, height in [('desktop',1440,1000),('mobile',390,844)]:
                page = browser.new_page(viewport={'width':width,'height':height},is_mobile=label=='mobile',has_touch=label=='mobile')
                seen = []
                page.on('request',lambda r:seen.append(r.url))
                page.goto(base+'/media')
                page.wait_for_selector('.pr-server-preview')
                page.wait_for_function('document.querySelector(".pr-art img").naturalWidth>0')
                assert page.locator('.pr-title').inner_text() == track['title']
                page.wait_for_timeout(400)  # settle native initial fade-in for visual evidence
                page.screenshot(path=str(out/f'{label}-native.png'),full_page=True)
                # No real audio decoder/stream is started, even for explicit control QA.
                page.evaluate('''() => {window.qaPlays=0;window.qaPauses=0;HTMLMediaElement.prototype.play=async function(){window.qaPlays++};HTMLMediaElement.prototype.pause=function(){window.qaPauses++};}''')
                next_track = {'id':'999999999','stream':'/radio/stream/999999999','title':'Synthetic queue continuation'}
                page.route('**/radio/queue',lambda r:r.fulfill(json={'tracks':[track,next_track]}))
                page.route('**/radio/stream/**',lambda r:r.abort())
                page.add_script_tag(path=str(ROOT/'assets/plex-radio.js'))
                page.wait_for_selector('#plex-radio')
                assert page.locator('#plex-radio .pr-title').inner_text() == track['title']
                assert page.locator('#plex-radio-audio').get_attribute('src') is None
                assert page.evaluate('window.qaPlays') == 0
                assert not any('/radio/' in url for url in seen)
                assert page.locator('#plex-radio img').evaluate('i=>i.naturalWidth>0')
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                page.wait_for_timeout(3200)  # several real native poll cycles
                assert page.locator('.plex-radio').count() == 1
                assert page.locator('#plex-radio .pr-title').inner_text() == track['title']
                page.screenshot(path=str(out/f'{label}-enhanced-idle.png'),full_page=True)
                page.locator('[data-action="play"]').click()
                page.wait_for_function('() => window.qaPlays===1')
                assert page.locator('#plex-radio-audio').get_attribute('src') == track['stream']
                page.evaluate("history.pushState({},'', '/hardware-workloads')")
                page.locator('[data-action="dismiss"]').click()
                assert page.locator('#plex-radio').is_hidden()
                assert page.evaluate('window.qaPauses') == 0
                page.evaluate("history.pushState({},'', '/media')")
                assert page.locator('#plex-radio').is_visible()
                page.locator('[data-action="shuffle"]').click()
                page.wait_for_function('() => window.qaPlays===2')
                assert page.locator('#plex-radio-audio').get_attribute('src') == next_track['stream']
                assert not any('/radio/stream/' in url for url in seen)
                report['screens'].append({'viewport':label,'initial_art_loaded':True,'initial_browser_radio_requests':0,'idle_play_calls':0,'explicit_stub_play_calls':page.evaluate('window.qaPlays'),'polling_stable':True,'dismiss_preserved_audio':True})
                page.close()
            # Independent synthetic failure: real native idle fallback remains usable.
            state.clear();state.update(track=None,error='Radio upstream unavailable')
            time.sleep(1.1)
            fallback=urllib.request.urlopen(base+'/api/pages/media/content/').read().decode()
            (out/'failure-server.html').write_text(fallback)
            assert 'Radio upstream unavailable' in fallback and 'Let your library play' in fallback
            page = browser.new_page()
            page.goto(base+'/media');page.wait_for_selector('.pr-server-preview')
            page.add_script_tag(path=str(ROOT/'assets/plex-radio.js'))
            assert 'Radio upstream unavailable' in page.locator('#plex-radio .pr-status').inner_text()
            assert page.locator('#plex-radio [data-action="play"]').is_enabled()
            assert page.locator('#plex-radio-audio').get_attribute('src') is None
            page.close()
            # Independent synthetic injection test; never label this as library data.
            state.update(track=dict(track,title='<img src=x onerror="window.QA_INJECTED=1">',artist='& <b>artist</b>',album='<script>window.QA_INJECTED=2</script>'),poster_base64=state.get('poster_base64',''),error='')
            time.sleep(1.1)
            escaped=urllib.request.urlopen(base+'/api/pages/media/content/').read().decode()
            (out/'synthetic-escaping-server.html').write_text(escaped)
            assert '<img src=x' not in escaped and '&lt;img' in escaped
            report['synthetic_failure_fallback']=True
            report['synthetic_metadata_escaped']=True
            browser.close()
        report['fixture_requests']=requests
        (out/'results.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        subprocess.run(['docker','logs',name],stdout=(out/'container.log').open('w'),stderr=subprocess.STDOUT)
        subprocess.run(['docker','rm','-f',name],check=True,capture_output=True)
        server.shutdown();server.server_close()

if __name__ == '__main__':
    main()
