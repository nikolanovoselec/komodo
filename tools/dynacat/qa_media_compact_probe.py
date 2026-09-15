"""Read-only live session discovery for compact-card QA."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--no-sandbox'])
        page=await b.new_page()
        responses=[]
        page.on('response',lambda r:responses.append(r.url))
        await page.goto('http://192.168.2.72:8080/media')
        await page.wait_for_selector('.mo-players')
        print(json.dumps({'sessions':await page.locator('.mo-player').count(),'now_playing':await page.locator('.mo-players').inner_text(),'responses':responses},indent=2))
        await page.screenshot(path='/tmp/media-compact-live.png',full_page=True)
        await b.close()
asyncio.run(main())
