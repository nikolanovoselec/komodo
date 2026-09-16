"""Native typed-art and changed polling test; captured art converted only for PNG coverage."""
import asyncio,base64,io,json
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright
import qa_arr_thumbnail as qa
async def main():
    source=qa.OUT/'source/captured';original=source.read_text();data=json.loads(original)
    image=Image.open(io.BytesIO(base64.b64decode(data['radarr']['data']['recent'][0]['poster'])))
    buf=io.BytesIO();image.save(buf,format='PNG')
    data['radarr']['data']['recent'][0].update(poster=base64.b64encode(buf.getvalue()).decode(),poster_mime='image/png')
    source.write_text(json.dumps(data))
    try:
        async with async_playwright() as p:
            b=await p.chromium.launch()
            page=await b.new_page(viewport={'width':390,'height':900},is_mobile=True,has_touch=True)
            await page.goto('http://127.0.0.1:18140/media')
            await page.wait_for_selector('.mo-import')
            thumb=page.locator('.mo-arr-delivery').nth(1).locator('.mo-arr-thumb img').first
            await thumb.scroll_into_view_if_needed();await thumb.evaluate('e=>e.decode()')
            assert (await thumb.get_attribute('src')).startswith('data:image/png;base64,')
            assert await thumb.evaluate('e=>e.naturalWidth>0')
            await page.locator('details').evaluate_all('es=>es.forEach(e=>e.open=true)')
            await page.locator('.mo-arr-delivery').nth(1).locator('.mo-item-title').first.focus()
            await page.wait_for_timeout(1200) # settle native smooth focus scrolling before measurement
            y=await page.evaluate('scrollY')
            for cycle in range(3):
                for app in data:data[app]['data']['recent'][0]['subtitle']='CHANGED POLL '+str(cycle)
                source.write_text(json.dumps(data))
                await page.wait_for_function('(n)=>[...document.querySelectorAll(".mo-recent-preview p")].filter(e=>e.textContent==="CHANGED POLL "+n).length===2',arg=cycle,timeout=20000)
                assert await page.locator('details').evaluate_all('es=>es.every(e=>e.open)')
                assert abs(await page.evaluate('scrollY')-y)<3
            await b.close()
        print('PASS native PNG decoding; 3 changed native polls; mobile scroll/focused link/disclosures retained')
    finally:source.write_text(original)
if __name__=='__main__':asyncio.run(main())
