"""Live rendering acceptance for the Flame-style directory. No external links followed."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get('DYNACAT_QA_BASE', 'http://127.0.0.1:18185').rstrip('/')
OUT = Path(os.environ.get('DYNACAT_QA_OUT', '/srv/hermes/workspaces/flame-directory-review'))
OUT.mkdir(parents=True, exist_ok=True)
ROOT = Path(__file__).parent
original = json.loads((ROOT / 'fixtures/endpoints-before-rebuild.json').read_text())
directory = json.loads((ROOT / 'endpoints-directory.json').read_text())
icon_doc = json.loads((ROOT / 'flame-mdi-icons.json').read_text())
assert len(original) == 77
assert sum(len(g['links']) for d in directory['domains'] if d['id'] != 'personal' for g in d['groups']) == 52
assert sum(len(g['links']) for d in directory['domains'] if d['id'] == 'personal' for g in d['groups']) == 25
personal = next(domain for domain in directory['domains'] if domain['id'] == 'personal')
expected_groups = [('news', 'News', 7), ('productivity-multimedia', 'Productivity & Multimedia', 8),
                   ('shopping', 'Shopping', 4), ('utilities', 'Utilities', 6)]
assert [(g['id'], g['title'], len(g['links'])) for g in personal['groups']] == expected_groups

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(viewport={'width':1600,'height':1100}, device_scale_factor=1)
    context.add_init_script("HTMLMediaElement.prototype.play = function(){ throw Error('Playback forbidden in directory QA'); };")
    context.route('**/radio/**', lambda route: route.abort())
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    for path in ['/', '/endpoints-services']:
        page.goto(BASE + path)
        page.wait_for_selector('.es-directory-v2[data-ready="true"]')
        assert page.locator('.es-applications .es-endpoint').count() == 52
        assert page.locator('.es-bookmarks .es-endpoint').count() == 25
        assert page.locator('.es-bookmarks .es-group').evaluate_all("groups=>groups.map(g=>[g.dataset.esGroup,g.querySelectorAll('.es-endpoint').length])") == [
            ['news', 7], ['productivity-multimedia', 8], ['shopping', 4], ['utilities', 6]
        ]

    pairs = page.locator('.es-endpoint').evaluate_all("rows => rows.map(a=>[a.querySelector('strong').textContent.trim(),a.getAttribute('href')])")
    assert sorted(pairs) == sorted([[item['name'], item['url']] for item in original])
    assert page.locator('.es-applications .es-endpoint strong').evaluate_all("nodes=>{const names=nodes.map(n=>n.textContent.trim());const c=new Intl.Collator(undefined,{sensitivity:'base',numeric:true});return names.every((n,i)=>i===0||c.compare(names[i-1],n)<=0)}")
    assert page.locator('.es-applications').evaluate("apps=>Boolean(apps.compareDocumentPosition(document.querySelector('.es-bookmarks'))&Node.DOCUMENT_POSITION_FOLLOWING)")
    assert page.locator('.es-toolbar, .es-search-row, .es-categories').count() == 0
    icons = page.locator('.es-icon-sprite symbol').evaluate_all("symbols=>symbols.map(s=>s.id).sort()")
    assert icons == sorted('es-mdi-' + name for name in icon_doc['icons'])
    assert page.locator('.es-endpoint').evaluate_all("links=>links.every(a=>a.querySelector('.es-icon use')?.getAttribute('href')===`#es-mdi-${a.dataset.esIcon}`)")

    samples = []
    for theme in ['midnight-navy', 'catppuccin-latte']:
        context.add_cookies([{'name':'theme','value':theme,'url':BASE}])
        for width in [1600, 1100, 900, 899, 700, 670, 669, 430, 429, 390]:
            page.set_viewport_size({'width':width,'height':1100 if width>500 else 844})
            page.goto(BASE + '/endpoints-services')
            page.wait_for_selector('.es-directory-v2[data-ready="true"]')
            page.wait_for_timeout(250)
            geometry = page.evaluate("""() => {
                const root=document.querySelector('.es-directory-v2');
                const links=[...root.querySelectorAll('.es-endpoint')];
                const appGrid=root.querySelector('.es-app-grid');
                const appLinks=[...root.querySelectorAll('.es-applications .es-endpoint')];
                const bookmarkLinks=[...root.querySelectorAll('.es-bookmarks .es-endpoint')];
                const appColumns=getComputedStyle(appGrid).gridTemplateColumns.split(' ').length;
                const luminance=color=>{const c=color.match(/\\d+(?:\\.\\d+)?/g).slice(0,3).map(Number).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2];};
                const contrast=(a,b)=>{const c=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (c[0]+.05)/(c[1]+.05);};
                const bg=getComputedStyle(document.body).backgroundColor;
                const title=getComputedStyle(root.querySelector('.es-applications .es-endpoint strong')).color;
                const description=getComputedStyle(root.querySelector('.es-applications .es-endpoint small')).color;
                const bookmark=getComputedStyle(root.querySelector('.es-bookmarks .es-endpoint strong')).color;
                return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                  appColumns:getComputedStyle(root.querySelector('.es-app-grid')).gridTemplateColumns.split(' ').length,
                  bookmarkColumns:getComputedStyle(root.querySelector('.es-group-grid')).gridTemplateColumns.split(' ').length,
                  containerWidth:root.getBoundingClientRect().width,
                  containerLeft:root.getBoundingClientRect().left,
                  parentWidth:root.parentElement.getBoundingClientRect().width,
                  parentLeft:root.parentElement.getBoundingClientRect().left,
                  paddingLeft:parseFloat(getComputedStyle(root).paddingLeft),
                  appIconWidth:root.querySelector('.es-applications .es-icon').getBoundingClientRect().width,
                  bookmarkIconWidth:root.querySelector('.es-bookmarks .es-icon').getBoundingClientRect().width,
                  appColumnGap:getComputedStyle(root.querySelector('.es-app-grid')).columnGap,
                  bookmarkColumnGap:getComputedStyle(root.querySelector('.es-group-grid')).columnGap,
                  descriptionSize:getComputedStyle(root.querySelector('.es-applications small')).fontSize,
                  appMarginBottom:parseFloat(getComputedStyle(appLinks[0]).marginBottom),
                  appRowPitch:appLinks[appColumns].getBoundingClientRect().top-appLinks[0].getBoundingClientRect().top,
                  appMinHit:Math.min(...appLinks.map(a=>a.getBoundingClientRect().height)),
                  bookmarkFontSize:getComputedStyle(bookmarkLinks[0].querySelector('strong')).fontSize,
                  bookmarkLineHeight:getComputedStyle(bookmarkLinks[0].querySelector('strong')).lineHeight,
                  bookmarkGap:getComputedStyle(bookmarkLinks[0]).gap,
                  bookmarkRowPitch:bookmarkLinks[1].getBoundingClientRect().top-bookmarkLinks[0].getBoundingClientRect().top,
                  bookmarkMinHit:Math.min(...bookmarkLinks.map(a=>a.getBoundingClientRect().height)),
                  minHit:Math.min(...links.map(a=>a.getBoundingClientRect().height)),
                  background:bg,accentContrast:contrast(title,bg),descriptionContrast:contrast(description,bg),bookmarkContrast:contrast(bookmark,bg),
                  iconCount:root.querySelectorAll('.es-endpoint svg.es-icon use').length};
            }""")
            assert page.locator('.es-endpoint').count() == 77
            expected_columns = 4 if width >= 900 else 3 if width >= 670 else 2 if width >= 430 else 1
            parent_width = geometry['parentWidth']
            if width < 769:
                expected_container_width, expected_padding = parent_width, 20
            elif width < 1201:
                expected_container_width, expected_padding = parent_width * 0.9, 20
            else:
                expected_container_width, expected_padding = min(parent_width * 0.9, 1714), 250
            expected_description_size = '10px' if 430 <= width <= 480 else '11px'
            assert geometry['scrollWidth'] <= width, geometry
            assert geometry['appMarginBottom'] == 14, geometry
            # Chromium can report 58.99997px for Flame's nominal 59px pitch.
            assert geometry['appRowPitch'] >= 58.9, geometry
            assert geometry['appMinHit'] >= 44, geometry
            assert geometry['bookmarkFontSize'] == '14px', geometry
            assert geometry['bookmarkLineHeight'] == '28px', geometry
            assert geometry['bookmarkGap'] == '2px', geometry
            expected_bookmark_height = 45 if width <= 760 else 28
            assert abs(geometry['bookmarkRowPitch'] - expected_bookmark_height) < 0.1, geometry
            # Browser fractional layout can shave a tiny amount off a 45px hit box.
            assert geometry['bookmarkMinHit'] >= expected_bookmark_height - 0.1, geometry
            assert geometry['appColumns'] == expected_columns, geometry
            assert geometry['bookmarkColumns'] == expected_columns, geometry
            assert abs(geometry['containerWidth'] - expected_container_width) < 1, geometry
            assert abs((geometry['containerLeft'] - geometry['parentLeft']) - (parent_width - geometry['containerWidth']) / 2) < 1, geometry
            assert abs(geometry['paddingLeft'] - expected_padding) < 1, geometry
            assert geometry['appIconWidth'] == 35, geometry
            assert geometry['bookmarkIconWidth'] == 20, geometry
            assert geometry['appColumnGap'] == '0px', geometry
            assert geometry['bookmarkColumnGap'] == '0px', geometry
            assert geometry['descriptionSize'] == expected_description_size, geometry
            assert geometry['accentContrast'] >= 4.5, geometry
            assert geometry['descriptionContrast'] >= 4.5, geometry
            assert geometry['bookmarkContrast'] >= 4.5, geometry
            page.screenshot(path=str(OUT / f'candidate-{width}-{theme}.png'), full_page=True)
            samples.append({'theme':theme, **geometry})

    mobile = browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True, device_scale_factor=1)
    mobile.route('**/radio/**', lambda route: route.abort())
    m = mobile.new_page()
    m.on('pageerror', lambda error: errors.append(str(error)))
    m.goto(BASE + '/endpoints-services')
    m.wait_for_selector('.es-directory-v2[data-ready="true"]')
    m.set_viewport_size({'width':1600,'height':1100})
    touch_desktop_geometry = m.evaluate("""() => ({width:innerWidth,coarsePointer:matchMedia('(pointer: coarse)').matches,
      appMinHit:Math.min(...[...document.querySelectorAll('.es-applications .es-endpoint')].map(a=>a.getBoundingClientRect().height)),
      bookmarkMinHit:Math.min(...[...document.querySelectorAll('.es-bookmarks .es-endpoint')].map(a=>a.getBoundingClientRect().height))})""")
    assert touch_desktop_geometry['coarsePointer']
    assert touch_desktop_geometry['appMinHit'] >= 44
    assert touch_desktop_geometry['bookmarkMinHit'] >= 44
    m.set_viewport_size({'width':390,'height':844})
    mobile_geometry = m.evaluate("""() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
      minHit:Math.min(...[...document.querySelectorAll('.es-endpoint')].map(a=>a.getBoundingClientRect().height)),
      bookmarkMinHit:Math.min(...[...document.querySelectorAll('.es-bookmarks .es-endpoint')].map(a=>a.getBoundingClientRect().height))})""")
    assert mobile_geometry['scrollWidth'] <= mobile_geometry['width']
    assert mobile_geometry['minHit'] >= 44
    assert mobile_geometry['bookmarkMinHit'] >= 44
    assert m.locator('.es-endpoint').count() == 77
    assert not errors, errors
    result = {
        'links':len(pairs),'applications':52,'bookmarks':25,'third_party_hosted_bookmarks':14,
        'mdi_icons':len(icon_doc['icons']),'urls_preserved':True,'alphabetical':True,
        'search_filter_chrome':False,'touch_mobile':True,'mobile_geometry':mobile_geometry,
        'touch_desktop_geometry':touch_desktop_geometry,
        'errors':errors,'layouts':samples,
    }
    (OUT / 'candidate-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='layouts'},indent=2))
    browser.close()
