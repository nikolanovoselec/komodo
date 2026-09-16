"""Native captured-real lower-page screenshots; Pi-hole blocked state is a labelled fixture.
Run with QA venv: python tools/dynacat/qa_networking_lower.py [--url live-networking-url]
Without --url, uses isolated candidate renderer and never deploys.
"""
import argparse
import json
from playwright.sync_api import sync_playwright
import test_networking_lower as tests


def capture(page, variant):
    report=[]
    for width in (1600,390):
        for theme,key in (('dark','midnight-navy'),('light','catppuccin-latte')):
            page.set_viewport_size({'width':width,'height':1100})
            page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
            page.wait_for_timeout(200)
            prefix=tests.OUT/f'{variant}-{theme}-{width}'
            page.screenshot(path=str(prefix)+'-page.png',full_page=True)
            if page.locator('.nw-lower').count():
                box=page.locator('.nw-lower').bounding_box()
                box['y']+=page.evaluate('scrollY')
                page.screenshot(path=str(prefix)+'-lower.png',clip=box,full_page=True)
            m=page.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth,
                clients:document.querySelectorAll('[data-nw-client]').length,
                graphs:Array.from(document.querySelectorAll('.nw-infrastructure svg path')).map(e=>e.getAttribute('d')),
                infrastructureHeight:document.querySelector('.nw-infrastructure').getBoundingClientRect().height,
                lowerColumns:getComputedStyle(document.querySelector('.nw-lower')||document.body).gridTemplateColumns,
                pihole:document.querySelector('.nw-pihole')?.innerText})''')
            m.update(width=width,theme=theme)
            report.append(m)
    (tests.OUT/f'{variant}-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps([{k:v for k,v in m.items() if k!='graphs'} for m in report],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url')
    args=parser.parse_args()
    if args.url:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page()
            page.add_init_script("HTMLMediaElement.prototype.play=function(){return Promise.reject(new Error('QA blocks audio'))}")
            page.goto(args.url)
            page.locator('.nw-lower').wait_for()
            capture(page,'live')
            browser.close()
    else:
        generator=tests.page.__wrapped__()
        page=next(generator)
        try: capture(page,'candidate')
        finally: generator.close()
