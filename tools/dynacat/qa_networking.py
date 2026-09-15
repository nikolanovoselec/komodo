"""Native Dynacat 3.0.0 renderer QA using explicitly synthetic contract data."""
import asyncio, copy, json, subprocess
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
OUT=ROOT.parents[2]/'networking-qa-evidence'

def prepare():
    (OUT/'config').mkdir(parents=True,exist_ok=True)
    (OUT/'source').mkdir(exist_ok=True)
    chart=dict(path='M0 24 L50 16 L100 20',dots=[],samples=3,scale=100,window_seconds=1800,state='ready')
    devices=[dict(id=str(i),name='SYNTHETIC '+name,model=model,kind=kind,state='ONLINE',ip='192.0.2.'+str(i+1),cpu_percent=12.5 if i!=2 else None,memory_percent=37.2,rx_mbps=0,tx_mbps=2.5,ports_active=3,ports_total=8,clients_count=12,history={k:dict(chart) for k in ('cpu','ram','rx','tx')}) for i,(name,model,kind) in enumerate([('Gateway','Example gateway','gateway'),('Office switch','Example switch','switch'),('Upstairs AP','Example AP','ap')])]
    devices[2]['history']['cpu']=dict(chart,path='',samples=0,state='unavailable')
    devices[1]['history']['rx']=dict(chart,path='',samples=1,state='collecting')
    data=dict(state='ready',error='',site=dict(id='fixture',name='SYNTHETIC CONTRACT · NOT LIVE'),summary=dict(devices_total=3,devices_online=3,clients_total=2,clients_wired=1,clients_wireless=1,networks_total=1,wifi_total=1),devices=devices,clients=[dict(id='c1',name='Example workstation',kind='wired',ip='192.0.2.10',network='Example LAN',device='Office switch',signal_dbm=None,rx_mbps=0,tx_mbps=None),dict(id='c2',name='Example phone',kind='wireless',ip='192.0.2.11',network='Example LAN',device='Upstairs AP',signal_dbm=-61,rx_mbps=1.2,tx_mbps=0.4)],networks=[dict(id='n1',name='Example LAN',vlan=10,subnet='192.0.2.0/24',purpose='corporate',enabled=True)],wifi=[dict(id='w1',name='Example WiFi',security='WPA2',bands=['2.4 GHz','5 GHz'],enabled=True)],wan=dict(available=False,state='unavailable',reason='WAN telemetry not exposed by this source'),capabilities=[dict(name='WAN telemetry',available=False,reason='Unsupported by source'),dict(name='Device inventory',available=True,reason='')],partial=True)
    (OUT/'source/network-current').write_text(json.dumps(data))
    cfg=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
    page=copy.deepcopy(next(p for p in cfg['pages'] if p.get('slug')=='networking'))
    page['columns'][0]['widgets'][0]['url']='http://networking-qa-source:8090/network-current'
    page['columns'][0]['widgets'][0]['cache']='1s'
    page['columns'][0]['widgets'][0]['update-interval']='1s'
    cfg['pages']=[dict(name=p['name'],slug=p['slug'],width='wide',**{'desktop-navigation-width':'wide'},columns=copy.deepcopy(page['columns'])) for p in cfg['pages'] if p.get('slug') in ('hardware-workloads','networking','media','endpoints-services')]
    cfg['document']['head']='<link rel="stylesheet" href="/assets/command-center.css"><link rel="stylesheet" href="/assets/networking.css"><script src="/assets/networking.js" defer></script><script src="/assets/command-center.js" defer></script>'
    cfg['theme'].pop('custom-css-file',None)
    cfg['server']['port']=8080
    cfg['server']['cache-dir']='/tmp/cache'
    (OUT/'config/dynacat.yml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    def docker(*args): return subprocess.run(['docker',*args],check=True,capture_output=True,text=True).stdout
    for name in ('networking-qa-stage','networking-qa-source'): subprocess.run(['docker','rm','-f',name],capture_output=True)
    docker('run','-d','--name','networking-qa-source','--network','media-compact-qa','-v',f'{OUT}/source:/data:ro','-w','/data','python:3.13-slim','python','-m','http.server','8090')
    docker('run','-d','--name','networking-qa-stage','--network','media-compact-qa','-p','127.0.0.1:18139:8080','-v',f'{OUT}/config:/app/config:ro','-v',f'{ROOT}/assets:/app/assets:ro','panonim/dynacat:3.0.0')

async def verify():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in (390,1600):
            for light in (False,True):
                page=await browser.new_page(viewport=dict(width=width,height=1000),is_mobile=width<600,has_touch=width<600)
                await page.goto('http://127.0.0.1:18139/networking')
                await page.wait_for_selector('.nw-dashboard',state='attached')
                assert 'SYNTHETIC CONTRACT' in await page.locator('.nw-dashboard').inner_text(), 'Site summary missing'
                if light: await page.locator('.theme-choices [data-key="catppuccin-latte"]').first.evaluate('e=>e.click()')
                assert await page.locator('.nw-device').count()==3
                assert await page.locator('.nw-device .nw-state.nw-warning').count()==0, 'Provider ONLINE must not be a warning'
                assert 'Unavailable' in await page.locator('.nw-device').nth(2).inner_text()
                assert 'Collecting' in await page.locator('.nw-device').nth(1).inner_text()
                assert '0.0 Mbps' in await page.locator('.nw-device').first.inner_text()
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.locator('[data-nw-disclosure="clients"] summary').click()
                await page.locator('[data-nw-search]').fill('phone')
                assert await page.locator('[data-nw-client]:visible').count()==1
                assert await page.locator('.nw-axis').first.inner_text() == '−30m\n0–100.0%\nnow'
                assert await page.locator('.nw-metric svg').first.get_attribute('viewBox') == '0 0 100 30'
                await page.locator('[data-nw-search]').evaluate('e=>e.setSelectionRange(1,3)')
                source=OUT/'source/network-current'
                changed=json.loads(source.read_text());changed['site']['name']=f'SYNTHETIC CONTRACT · REFRESH {width} {light}'
                source.write_text(json.dumps(changed))
                await page.wait_for_function('(name)=>document.querySelector(".nw-heading h2")?.textContent===name',arg=changed['site']['name'])
                assert await page.locator('[data-nw-disclosure="clients"]').evaluate('e=>e.open')
                assert await page.locator('[data-nw-search]').input_value()=='phone'
                assert await page.locator('[data-nw-search]').evaluate('e=>e===document.activeElement && e.selectionStart===1 && e.selectionEnd===3'), await page.locator('[data-nw-search]').evaluate('e=>({active:e===document.activeElement,start:e.selectionStart,end:e.selectionEnd,tag:document.activeElement.outerHTML})')
                assert await page.locator('[data-nw-client]:visible').count()==1
                await page.locator('[data-nw-disclosure="firewall"] summary').click()
                assert 'Firewall rules unavailable' in await page.locator('[data-nw-disclosure="firewall"]').inner_text()
                await page.evaluate('scrollTo(0,0)')
                await page.screenshot(path=str(OUT/f'networking-{width}-{"light" if light else "dark"}.png'),full_page=True)
                for el in await page.locator('.nw-dashboard summary,.nw-dashboard input,.nw-dashboard select').all():
                    assert (await el.bounding_box())['height']>=44
                await page.close()
        source=OUT/'source/network-current'; changed=json.loads(source.read_text())
        changed['firewall']=dict(available=True,rules=[dict(id='r1',name='SYNTHETIC deny guest to LAN',enabled=False,action='drop',source='Example guest',destination='Example LAN',protocol='TCP',port='443')])
        changed['devices'][0]['history']['cpu']['dots']=[dict(x=25,y=12)]
        source.write_text(json.dumps(changed))
        page=await browser.new_page();await page.goto('http://127.0.0.1:18139/networking')
        await page.locator('[data-nw-disclosure="firewall"] summary').click()
        await page.wait_for_function('()=>document.querySelector(".nw-firewall")?.textContent.includes("SYNTHETIC deny")')
        assert 'Disabled' in await page.locator('.nw-firewall').inner_text()
        assert await page.locator('.nw-metric circle').first.get_attribute('cx')=='25'
        changed.update(state='unavailable',error='SYNTHETIC source unavailable',summary={},devices=[],clients=[],networks=[],wifi=[],firewall={})
        source.write_text(json.dumps(changed))
        await page.wait_for_function('()=>document.querySelector(".nw-dashboard")?.textContent.includes("SYNTHETIC source unavailable")')
        assert await page.locator('.nw-device').count()==0
        assert await page.locator('.nw-summary b').all_text_contents()==['—']*7
        await page.close();await browser.close()
    print('PASS native synthetic contract: desktop/mobile dark/light, null vs zero, axes/sparse histories, actual refresh caret/search/disclosures, firewall branches, unavailable state, targets/overflow')

if __name__=='__main__':
    try:
        prepare()
        asyncio.run(verify())
    finally:
        for name in ('networking-qa-stage','networking-qa-source'):
            subprocess.run(['docker','rm','-f',name],capture_output=True)
