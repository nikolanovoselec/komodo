"""Captured-production networking layout QA; never deploys or starts playback.

Run with dynacat-qa-venv/bin/python tools/dynacat/qa_networking_layout.py baseline
(or candidate, or live --url http://HOST:8080/networking). Baseline uses the
production backup; candidate uses repository config/assets. Captured JSON stays
read-only. Evidence and generated QA config live in networking-layout-qa/.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parents[1] / 'networking-layout-qa'
SOURCE = OUT / 'source/network-current'
NAMES = ('networking-layout-renderer', 'networking-layout-source')


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def cleanup():
    for name in NAMES:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)


def prepare(variant, port):
    origin = OUT / 'backup' if variant == 'baseline' else ROOT
    cfg = yaml.safe_load((origin / 'config/dynacat.yml').read_text())
    page = copy.deepcopy(next(p for p in cfg['pages'] if p.get('slug') == 'networking'))
    widgets = [w for c in page['columns'] for w in c['widgets']]
    network = [w for w in widgets if 'network-current' in w.get('url', '')]
    if len(network) != 1:
        raise ValueError('Expected exactly one captured-network widget')
    # No other widgets (and therefore no radio/feed backends) run in this harness.
    for col in page['columns']:
        col['widgets'] = [w for w in col['widgets'] if w is network[0]]
    page['columns'] = [c for c in page['columns'] if c['widgets']]
    network[0].update(url='http://networking-layout-source:8090/network-current',
                      cache='1s', **{'update-interval': '2s'})
    cfg['pages'] = [page]
    cfg['server'].update(port=8080, **{'cache-dir': '/tmp/cache'})
    # Keep production document.head intact, including normal theme/navigation JS.
    folder = OUT / variant
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'dynacat.yml').write_text(yaml.safe_dump(cfg, sort_keys=False))
    cleanup()
    docker('network', 'inspect', 'media-compact-qa')
    docker('run', '-d', '--name', NAMES[1], '--network', 'media-compact-qa',
           '-v', f'{OUT}/source:/data:ro', '-w', '/data', 'python:3.13-slim',
           'python', '-m', 'http.server', '8090')
    docker('run', '-d', '--name', NAMES[0], '--network', 'media-compact-qa',
           '-p', f'127.0.0.1:{port}:8080', '-v', f'{folder}:/app/config:ro',
           '-v', f'{origin}/assets:/app/assets:ro', 'panonim/dynacat:3.0.0')


MEASURE = """() => {
 const all=s=>Array.from(document.querySelectorAll(s));
 const rect=e=>{const r=e.getBoundingClientRect();return {height:r.height,width:r.width,x:r.x,y:r.y}};
 return {
  section:rect(document.querySelector('.nw-dashboard')),
  devices:all('.nw-device').map(e=>({name:e.querySelector('h4')?.textContent.trim(),...rect(e)})),
  gateway:all('.nw-gateway').map(rect),
  groups:all('.nw-group').map(e=>({heading:e.querySelector('h2,h3,h4')?.textContent.trim(),...rect(e)})),
  compactRows:all('.nw-group .nw-device').map(rect),
  charts:all('.nw-metric svg').map(rect),
  areas:all('.nw-area').map(e=>({path:e.getAttribute('d'),fill:getComputedStyle(e).fill,opacity:getComputedStyle(e).fillOpacity})),
  disclosures:all('[data-nw-disclosure]').map(e=>e.dataset.nwDisclosure),
  overflow:document.documentElement.scrollWidth>innerWidth,
  overflowingElements:all('.nw-dashboard *').filter(e=>{let r=e.getBoundingClientRect();return r.width && (r.right>innerWidth+1||r.left< -1)}).map(e=>({tag:e.tagName,classes:e.className.baseVal??e.className})),
  viewport:{width:innerWidth,height:innerHeight,mobile:matchMedia('(pointer:coarse)').matches},
  background:getComputedStyle(document.body).backgroundColor
 };
}"""


async def inspect(args, report):
    source = json.loads(SOURCE.read_text())
    baseline_path = OUT / 'baseline-report.json'
    baseline = json.loads(baseline_path.read_text()) if args.variant == 'candidate' and baseline_path.exists() else None
    url = args.url if args.variant == 'live' else f'http://127.0.0.1:{args.port}/networking'
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for width in (1600, 390):
            for theme, key in (('dark', 'midnight-navy'), ('light', 'catppuccin-latte')):
                context = await browser.new_context(viewport={'width': width, 'height': 1100},
                    is_mobile=width == 390, has_touch=width == 390, device_scale_factor=1,
                    color_scheme=theme, service_workers='block')
                # Block audio even if a retained head script attempts automatic playback.
                await context.add_init_script("HTMLMediaElement.prototype.play=function(){return Promise.reject(new DOMException('Playback blocked by QA','NotAllowedError'))}")
                blocked = []
                async def guard(route):
                    req = route.request
                    if req.resource_type == 'media' or re.search(r'(?:stream|transcode|/audio|/radio/)', req.url, re.I):
                        blocked.append(req.url)
                        await route.abort()
                    elif urlsplit(req.url).netloc != urlsplit(url).netloc:
                        blocked.append(req.url)
                        await route.abort()
                    else:
                        await route.continue_()
                await context.route('**/*', guard)
                page = await context.new_page()
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                for attempt in range(30):
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                        await page.wait_for_selector('.nw-device', timeout=3000)
                        break
                    except Exception:
                        if attempt == 29:
                            raise
                        await asyncio.sleep(.3)
                await page.locator(f'.theme-choices [data-key="{key}"]').first.evaluate('e=>e.click()')
                await page.wait_for_timeout(350)
                m = await page.evaluate(MEASURE)
                m.update(width=width, theme=theme, errors=errors, blockedRequests=blocked, checks={})
                report['measurements'].append(m)
                def check(name, ok):
                    m['checks'][name] = bool(ok)
                check('seven_devices', len(m['devices']) == 7)
                check('no_page_overflow', not m['overflow'])
                check('no_device_element_overflow', not m['overflowingElements'])
                check('mobile_emulation', m['viewport']['mobile'] == (width == 390))
                if args.variant != 'live':
                    check('captured_device_names', sorted(d['name'] for d in m['devices']) == sorted(d['name'] for d in source['devices']))
                if args.variant != 'live':
                    # Compare source paths verbatim: null intervals must not acquire bridges.
                    for device in source['devices']:
                        card = page.locator('.nw-device').filter(has=page.locator('h4', has_text=re.compile('^' + re.escape(device['name']) + '(?: ↗)?$')))
                        check('device_once_' + device['id'], await card.count() == 1)
                        metrics = card.locator('.nw-metric')
                        for index, (key, field, unit) in enumerate((('cpu', 'cpu_percent', '%'), ('ram', 'memory_percent', '%'), ('rx', 'rx_mbps', ' Mbps'), ('tx', 'tx_mbps', ' Mbps'))):
                            metric = metrics.nth(index)
                            value = device.get(field)
                            expected_value = 'Unavailable' if value is None else f'{value:.1f}{unit}'
                            check('value_' + device['id'] + key, await metric.locator('b').inner_text() == expected_value)
                            history = device['history'][key]
                            if history.get('samples', 0) > 1 and history.get('path'):
                                check('path_' + device['id'] + key, await metric.locator('svg path:not(.nw-gridline):not(.nw-area)').get_attribute('d') == history['path'])
                                if args.variant == 'candidate' and history.get('area_path'):
                                    check('area_' + device['id'] + key, await metric.locator('.nw-area').get_attribute('d') == history['area_path'])
                prefix = OUT / f'{args.variant}-{theme}-{width}'
                await page.screenshot(path=f'{prefix}-page.png', full_page=True)
                await page.locator('.nw-dashboard').screenshot(path=f'{prefix}-network.png')
                if args.variant in ('candidate', 'live'):
                    check('gateway_prominent', len(m['gateway']) == 1 and bool(m['compactRows']) and m['gateway'][0]['height'] > max(r['height'] for r in m['compactRows']))
                    check('group_headings', [g['heading'].casefold() for g in m['groups']] == ['switches', 'access points', 'internet backup'])
                    check('six_compact_rows', len(m['compactRows']) == 6)
                    check('filled_chart_areas', bool(m['areas']) and all(a['path'] and a['fill'] not in ('none', 'transparent', 'rgba(0, 0, 0, 0)') and float(a['opacity']) > 0 for a in m['areas']))
                    if baseline:
                        old = next(v for v in baseline['measurements'] if v['width'] == width and v['theme'] == theme)
                        m['sectionReductionPx'] = old['section']['height'] - m['section']['height']
                        check('section_shorter_than_baseline', m['sectionReductionPx'] > 0)
                        check('rows_shorter_than_baseline', bool(m['compactRows']) and max(r['height'] for r in m['compactRows']) < min(d['height'] for d in old['devices']))
                # Keyboard-operable disclosures and actual captured client search.
                for disclosure in m['disclosures']:
                    details = page.locator(f'[data-nw-disclosure="{disclosure}"]')
                    summary = details.locator('summary').first
                    await summary.focus()
                    await page.keyboard.press('Enter')
                    check(f'disclosure_{disclosure}_opens', await details.evaluate('e=>e.open'))
                    await page.keyboard.press('Enter')
                    check(f'disclosure_{disclosure}_closes', not await details.evaluate('e=>e.open'))
                await page.locator('[data-nw-disclosure="clients"] summary').click()
                search = page.locator('[data-nw-search]')
                rows = page.locator('[data-nw-client]')
                texts = await rows.all_text_contents()
                query = source['clients'][0]['ip']
                await search.fill(query)
                expected = sum(query.casefold() in text.casefold() for text in texts)
                check('client_search', expected > 0 and await page.locator('[data-nw-client]:visible').count() == expected)
                # Exercise the public restoration event without fabricating network data.
                await page.evaluate("document.dispatchEvent(new CustomEvent('dynacat:widget-updated'))")
                check('search_disclosure_restore_event', await search.input_value() == query and await page.locator('[data-nw-disclosure="clients"]').evaluate('e=>e.open'))
                await search.fill('QA-no-such-client-4b821')
                check('search_no_results', await page.locator('[data-nw-client]:visible').count() == 0)
                await search.fill('')
                check('search_clear_restores', await page.locator('[data-nw-client]:visible').count() == len(texts))
                check('no_js_errors', not errors)
                m['clientRows'] = len(texts)
                m['minimumControlHeight'] = await page.locator('.nw-dashboard summary,.nw-dashboard input,.nw-dashboard select').evaluate_all('es=>Math.min(...es.filter(e=>e.getBoundingClientRect().height).map(e=>e.getBoundingClientRect().height))')
                check('44px_controls', m['minimumControlHeight'] >= 44)
                await page.locator('[data-nw-disclosure="clients"] summary').click()
                await context.close()
        await browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variant', choices=('baseline', 'candidate', 'live'))
    parser.add_argument('--port', type=int, default=18145)
    parser.add_argument('--url', default='http://192.168.2.72:8080/networking')
    args = parser.parse_args()
    report = dict(variant=args.variant, source=str(SOURCE),
                  sourceSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  sourceType='captured production' if args.variant != 'live' else 'live production',
                  measurements=[])
    try:
        if args.variant != 'live':
            prepare(args.variant, args.port)
        asyncio.run(inspect(args, report))
    except Exception as exc:
        report['fatal'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if args.variant != 'live':
            cleanup()
        report['sourceUnchanged'] = report['sourceSha256'] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        report['passed'] = bool(report['measurements']) and len(report['measurements']) == 4 and report['sourceUnchanged'] and 'fatal' not in report and all(all(m['checks'].values()) for m in report['measurements'])
        (OUT / f'{args.variant}-report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
