"""Captured native baseline/candidate, and read-only live node reference."""
import sys,subprocess,json
from pathlib import Path
from playwright.sync_api import sync_playwright
import test_networking_lower as t
if len(sys.argv)>1 and sys.argv[1]=='reference':
 with sync_playwright() as p:
  b=p.chromium.launch(); page=b.new_page(viewport={'width':1600,'height':1100})
  page.goto('http://192.168.2.72:8080/hardware-workloads');page.wait_for_timeout(2500)
  page.screenshot(path='pihole-continuous-qa/nodes-reference.png',full_page=True)
  print(page.locator('h2,h3').all_text_contents());b.close()
else:
 g=t.page.__wrapped__()
 try:
  next(g)
  subprocess.run([sys.executable,'tools/dynacat/qa_pihole_redesign.py','http://127.0.0.1:18146/networking',sys.argv[1]],check=True)
 finally:g.close()
