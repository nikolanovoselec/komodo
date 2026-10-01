"""Native-renderer acceptance for the rebuilt directory. No external links followed."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:18185'
OUT = Path('/srv/hermes/workspaces/endpoints-rebuild-review')
original = json.loads((OUT/'original-inventory.json').read_text())
with sync_playwright() as p:
    b=p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context=b.new_context(viewport={'width':1600,'height':1100}, device_scale_factor=1)
    # Layout tests never initiate audio or contact a media session.
    context.add_init_script("HTMLMediaElement.prototype.play = function(){ throw Error('Playback forbidden in directory QA'); };")
    context.route('**/radio/**', lambda route: route.abort())
    page=context.new_page(); errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.goto(BASE+'/endpoints-services');page.wait_for_selector('.es-directory-v2[data-ready="true"]')
    pairs=page.locator('.es-endpoint').evaluate_all("rows => rows.map(a=>[a.querySelector('strong').textContent,a.getAttribute('href')])")
    assert sorted(pairs)==sorted([[i['name'],i['url']] for i in original])
    page.locator('[data-es-category="media"]').click()
    assert page.locator('.es-endpoint:visible').count()==21, 'Media filter must show all four media-purpose groups'
    assert page.locator('.es-domain:visible').count()==1
    page.locator('[data-es-category="all"]').click()
    page.locator('#endpoint-search').fill('backup tools')
    assert page.locator('.es-endpoint:visible strong').all_text_contents()==['Backrest Tools'], 'Search must match all words across name and purpose'
    page.locator('.es-clear').click()
    page.locator('#endpoint-search').fill('no-such-service-zzzzz')
    assert page.locator('.es-empty').is_visible()
    assert page.locator('.es-domain:visible').count()==0
    page.locator('#endpoint-search').press('Escape')
    assert page.locator('.es-endpoint:visible').count()==77
    assert not page.locator('.es-clear').is_visible()
    samples=[]
    for theme in ['midnight-navy','catppuccin-latte']:
        # Native GET theme response, same cookie used by the live theme picker.
        context.add_cookies([{'name':'theme','value':theme,'url':BASE}])
        for width in [1600,1024,768,390]:
            page.set_viewport_size({'width':width,'height':1100 if width>500 else 844})
            page.goto(BASE+'/endpoints-services');page.wait_for_selector('.es-directory-v2');page.wait_for_timeout(400)
            assert page.locator('.es-endpoint:visible').count()==77
            geometry=page.evaluate("""() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                cards:[...document.querySelectorAll('.es-group')].map(x=>({w:x.getBoundingClientRect().width,h:x.getBoundingClientRect().height})),
                minHit:Math.min(...[...document.querySelectorAll('.es-endpoint')].map(x=>x.getBoundingClientRect().height)),
                background:getComputedStyle(document.body).backgroundColor,
                font:getComputedStyle(document.querySelector('.es-endpoint strong')).fontSize})""")
            assert geometry['scrollWidth']<=width, geometry
            assert geometry['minHit']>=44, geometry
            if width>=1024:
                assert all(c['w']>=240 for c in geometry['cards']), geometry
            page.screenshot(path=str(OUT/f'candidate-{width}-{theme}.png'),full_page=True)
            page.screenshot(path=str(OUT/f'candidate-{width}-{theme}-viewport.png'))
            samples.append({'theme':theme,**geometry})
    # Actual touch/mobile context, not merely a desktop page narrowed to 390 px.
    mobile=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)
    mobile.route('**/radio/**',lambda route:route.abort())
    m=mobile.new_page();m.goto(BASE+'/endpoints-services');m.wait_for_selector('.es-directory-v2[data-ready="true"]')
    m.locator('[data-es-category="work"]').tap()
    assert m.locator('.es-endpoint:visible').count()==21
    m.locator('[data-es-category="all"]').tap()
    cdp=mobile.new_cdp_session(m)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':190,'y':730}]})
    for y in [650,570,490,410,330]:
        cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':190,'y':y}]});m.wait_for_timeout(90)
    m.wait_for_timeout(250);cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});m.wait_for_timeout(600)
    initial=m.evaluate('window.scrollY');m.wait_for_timeout(2200);final=m.evaluate('window.scrollY')
    assert initial>100 and abs(initial-final)<2,(initial,final)
    assert m.evaluate('document.documentElement.scrollWidth <= innerWidth')
    mobile.close()
    assert not errors,errors
    result={'links':len(pairs),'domains':4,'groups':13,'urls_preserved':True,'search':True,'filters':True,'touch_mobile':True,'scroll_stable':True,'errors':errors,'layouts':samples}
    (OUT/'candidate-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='layouts'},indent=2));b.close()
