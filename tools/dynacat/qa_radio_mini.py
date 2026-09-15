"""Read-only live-shell/local-CSS mini-player QA. Synthetic metadata; audio stubbed.
Run: python qa_radio_mini.py URL OUTPUT [--baseline] [--inspect]
No real radio requests or playback are allowed. --inspect records without assertions.
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
STUB = """(() => {
 window.__audioCalls={play:0,pause:0};
 HTMLMediaElement.prototype.play=function(){window.__audioCalls.play++;return Promise.resolve()};
 HTMLMediaElement.prototype.pause=function(){window.__audioCalls.pause++};
 HTMLMediaElement.prototype.load=function(){};
})();"""
GEOMETRY = """e=>{
 const box=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};
 const card=box(e),buttons=[...e.querySelectorAll('.pr-controls button')].map(box);
 return {card,buttons,dismiss:box(e.querySelector('.pr-dismiss')),rightBlank:card.right-buttons.at(-1).right,
 overflow:document.documentElement.scrollWidth>innerWidth};
}"""

def main():
    url, output = sys.argv[1:3]
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    inspect = '--inspect' in sys.argv
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (1440, 390, 320):
            for theme in ('dark', 'light'):
                context = browser.new_context(viewport={'width': width, 'height': 900},
                                              is_mobile=width < 600, has_touch=width < 600)
                context.add_init_script(STUB)
                page = context.new_page()
                blocked = []
                def block(route):
                    blocked.append(route.request.url)
                    route.abort()
                page.route('**/radio/**', block)
                if '--baseline' not in sys.argv:
                    page.route('**/assets/plex-radio.css*', lambda route: route.fulfill(
                        path=str(ROOT/'assets/plex-radio.css'), content_type='text/css'))
                page.goto(url+'/media')
                card = page.locator('#plex-radio'); card.wait_for()
                page.evaluate("""() => {
                  document.querySelector('.pr-title').textContent='Synthetic fixture — a long radio track title';
                  document.querySelector('.pr-artist').textContent='Fixture artist / no real playback';
                  document.querySelector('.pr-art img').hidden=true;
                  window.__fixtureAudio=document.querySelector('#plex-radio-audio');
                }""")
                assert page.evaluate('window.__audioCalls.play===0')
                key = 'default' if theme == 'dark' else 'default-light'
                page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
                page.wait_for_timeout(250)
                assert page.evaluate('document.documentElement.dataset.theme') == key
                main_before = card.evaluate('e=>[e.offsetWidth,e.offsetHeight]')
                page.evaluate("history.pushState({},'', '/hardware-workloads')")
                page.wait_for_timeout(150)
                geometry = card.evaluate(GEOMETRY)
                label = f'{width}-{theme}'
                card.screenshot(path=str(out/f'{label}-mini.png'))
                row = {'fixture': 'Synthetic metadata, stubbed audio; live page shell',
                       'css': 'live baseline' if '--baseline' in sys.argv else 'local candidate',
                       'mainGeometry': main_before, 'width': width, 'theme': theme, **geometry}
                rows.append(row)
                (out/'report.json').write_text(json.dumps(rows, indent=2))
                if not inspect:
                    assert geometry['card']['width'] <= (360 if width > 600 else 320), geometry
                    assert geometry['rightBlank'] <= 56, geometry
                    assert not geometry['overflow'], geometry
                    for box in geometry['buttons']+[geometry['dismiss']]:
                        assert box['width'] >= 44 and box['height'] >= 44, box
                        assert box['x'] >= geometry['card']['x'] and box['right'] <= geometry['card']['right'], box
                        assert box['y'] >= geometry['card']['y'] and box['bottom'] <= geometry['card']['bottom'], box
                    assert all(b['bottom'] <= geometry['dismiss']['y'] or b['y'] >= geometry['dismiss']['bottom'] or b['right'] <= geometry['dismiss']['x'] for b in geometry['buttons'])
                dismiss = page.get_by_role('button', name='Dismiss mini player')
                dismiss.focus(); dismiss.press('Enter')
                assert card.is_hidden()
                page.evaluate("history.pushState({},'', '/endpoints-services')")
                assert card.is_hidden()
                page.evaluate("history.pushState({},'', '/media')")
                assert card.is_visible() and dismiss.is_hidden()
                assert card.evaluate('e=>[e.offsetWidth,e.offsetHeight]') == main_before
                assert page.evaluate('window.__fixtureAudio===document.querySelector("#plex-radio-audio")')
                assert page.evaluate('window.__audioCalls.play===0 && window.__audioCalls.pause===0')
                assert not blocked, blocked
                row['dismiss_keyboard_persistence_return_no_autoplay'] = True
                context.close()
        browser.close()
    (out/'report.json').write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))

if __name__ == '__main__':
    main()
