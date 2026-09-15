"""Exercise real Media projections and navigation; no fake data or playback writes."""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

def navigation_destination(expected, actual):
    """Exact item route or a known authentication gate, never arbitrary redirects."""
    if actual == expected:
        return actual, False
    source, destination = urlsplit(expected), urlsplit(actual)
    plex = source.scheme == 'https' and source.netloc in {'app.plex.tv', 'plex.novoselec.ch'}
    protected = source.scheme == 'https' and source.netloc in {
        'sonarr.graymatter.ch', 'radarr.graymatter.ch', 'qbittorrent.graymatter.ch',
        'plex.novoselec.ch', 'emby.novoselec.ch', 'jellyfin.novoselec.ch'}
    allowed = destination.scheme == 'https' and (
        (plex and destination.netloc == 'app.plex.tv' and destination.path == '/auth/') or
        (protected and destination.netloc == 'authentik.graymatter.ch' and
         destination.path == '/if/flow/default-authentication-flow/'))
    # Redirect query/hash can contain authentication state; never emit them.
    assert allowed, 'Unexpected popup destination (not the requested URL or known authentication route)'
    return destination._replace(query='', fragment='').geturl(), True


async def verify_popup(popup, expected, errors):
    await popup.wait_for_load_state('domcontentloaded', timeout=25000)
    await popup.wait_for_timeout(1200)
    assert not errors, errors
    assert await popup.evaluate('window.opener===null'), 'Opener exposed'
    return navigation_destination(expected, popup.url)


async def main():
    from playwright.async_api import async_playwright
    base=sys.argv[1].rstrip('/'); out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1600,'height':1100})
        errors=[];writes=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:writes.append(r.url) if r.method!='GET' else None)
        await page.goto(base+'/media')
        await page.wait_for_selector('.mo-traffic svg')
        await page.wait_for_selector('.mo-poster-link')
        await page.wait_for_timeout(12000)
        counts=await page.evaluate('''() => ({playing:document.querySelectorAll('.mo-player').length,playingLinks:document.querySelectorAll('a.mo-player-link').length,library:document.querySelectorAll('.mo-poster').length,libraryLinks:document.querySelectorAll('.mo-poster-link').length,imports:document.querySelectorAll('.mo-import').length,importLinks:document.querySelectorAll('.mo-import .mo-item-title').length})''')
        assert counts['playing']==counts['playingLinks'],counts
        assert counts['library']==counts['libraryLinks'] and counts['library']>0,counts
        assert counts['imports']==counts['importLinks'],counts
        link_records=await page.locator('.mo-page a').evaluate_all('''els=>els.map(a=>({href:a.href,rel:a.rel,target:a.target,poster:!!a.querySelector('img'),title:!!a.querySelector('h3'),cls:a.className}))''')
        for link in link_records:
            assert link['target']=='_blank' and 'noopener' in link['rel'],link
            assert urlsplit(link['href']).scheme=='https',link
            assert not any(s in link['href'].lower() for s in ['token','192.168.','session=','apikey','api_key']),link
        for a in await page.locator('.mo-poster').all():
            assert await a.locator('.mo-poster-link').get_attribute('href') == await a.locator('.mo-item-title').get_attribute('href')
        await page.evaluate("window.updates=[];document.addEventListener('dynacat:widget-updated',e=>{if(e.detail.widget.querySelector('.mo-live'))updates.push(performance.now())})")
        focus_selector='a.mo-player-link' if counts['playing'] else '.mo-poster-link'
        focus=page.locator(focus_selector).first
        await focus.focus(); href=await focus.get_attribute('href')
        before=await page.locator('.mo-traffic-foot').inner_text()
        path_before=await page.locator('.mo-traffic-rx path').get_attribute('d')
        await page.wait_for_timeout(22000)
        assert await page.evaluate('document.activeElement.getAttribute("href")')==href,'Focus lost'
        cadence=await page.evaluate('updates.slice(1).map((v,i)=>v-updates[i])')
        assert len(cadence)>8 and max(cadence)<2500,cadence
        after=await page.locator('.mo-traffic-foot').inner_text()
        path_after=await page.locator('.mo-traffic-rx path').get_attribute('d')
        assert before!=after and path_before!=path_after,(before,after)
        assert await page.locator('.mo-traffic-rx circle').count()>=2
        clicks=[]
        popup_errors=[]
        def watch_popup(popup):
            popup.on('pageerror', lambda error: popup_errors.append('Popup JavaScript error'))
            popup.on('requestfailed', lambda request: popup_errors.append('Popup navigation failed')
                     if request.is_navigation_request() else None)
            popup.on('response', lambda response: popup_errors.append('Popup HTTP error ' + str(response.status))
                     if response.request.is_navigation_request() and response.status >= 400 else None)
        page.context.on('page', watch_popup)
        # Only dashboard writes are prohibited; Plex auth startup may POST.

        # Actual poster and title activations. Never click a Plex play/control button.
        selectors=(([ 'a.mo-player-link img', 'a.mo-player-link h3' ] if counts['playing'] else [])+
                   ['.mo-poster-link img','.mo-poster .mo-item-title',
                    '.mo-import .mo-item-title', '.mo-delivery h3 a', '.mo-server'])
        for selector in selectors:
            element=page.locator(selector).first
            expected=await element.evaluate('e=>e.closest("a").href')
            async with page.expect_popup() as event:
                await element.click()
            popup=await event.value
            final, authentication_required = await verify_popup(popup, expected, popup_errors)
            clicks.append(dict(selector=selector,expected=expected,final_url=final,title=await popup.title(),authentication_required=authentication_required or 'sign in' in (await popup.locator('body').inner_text()).lower()))
            await popup.close();await page.bring_to_front()
        variants=[]
        for theme in ['catppuccin-latte','midnight-navy']:
            await page.locator('.header-container .theme-picker').hover()
            await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click()
            await page.wait_for_timeout(500);await page.reload();await page.wait_for_selector('.mo-traffic svg')
            assert await page.locator('html').get_attribute('data-theme')==theme
            for width,height in [(1600,1100),(1024,1000),(768,1000),(390,844)]:
                await page.set_viewport_size({'width':width,'height':height})
                await page.evaluate('scrollTo(0,0)');await page.wait_for_timeout(500)
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
                file=f'{width}-{theme}.png';await page.screenshot(path=str(out/file),full_page=True)
                if width==1600:await page.locator('.mo-traffic').screenshot(path=str(out/f'bandwidth-{theme}.png'))
                variants.append(file)
            await page.set_viewport_size({'width':1600,'height':1100})
        imgs=await page.locator('.mo-poster img,.mo-player img').evaluate_all('imgs=>({count:imgs.length,loaded:imgs.filter(i=>i.complete&&i.naturalWidth).length,safe:imgs.every(i=>i.src.startsWith("data:image/jpeg;base64,"))})')
        assert imgs['loaded']==imgs['count'] and imgs['safe'],imgs
        await page.goto(base+'/endpoints-services');await page.wait_for_selector('.es-launcher')
        text=await page.locator('body').inner_text()
        assert 'News desk' not in text and 'Article integration pending' in text,text[-1500:]
        await page.screenshot(path=str(out/'news-pending.png'),full_page=True)
        assert not errors,errors
        assert not writes,writes
        result=dict(counts=counts,links=link_records,clicks=clicks,images=imgs,graph_before=before,graph_after=after,graph_changed=True,focus_preserved=True,cadence_ms=cadence,variants=variants,errors=errors,writes=writes)
        (out/'report.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k!='links'},indent=2))
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
