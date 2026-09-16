"""Offline evidence summaries and baseline/candidate review sheets."""
from pathlib import Path
import json, hashlib, re, subprocess
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'cohesive-qa'
base=json.loads((OUT/'baseline-report.json').read_text());candidate=json.loads((OUT/'candidate-report.json').read_text())
rows=[]
for a,b in zip(base,candidate):
    slug=b['slug'];width=b['width'];theme=b['theme'];suffix='widget' if slug=='hardware-workloads' else 'page'
    files=[OUT/f'{v}-{slug}-{theme}-{width}-{suffix}.png' for v in ('baseline','candidate')]
    images=[Image.open(p).convert('RGB') for p in files]
    target=1000 if width==1600 else 390
    images=[im.resize((target,round(im.height*target/im.width))) for im in images]
    canvas=Image.new('RGB',(2*target+36,max(im.height for im in images)+55),'#e0e3e9');draw=ImageDraw.Draw(canvas)
    for i,im in enumerate(images):
        x=12+i*(target+12);draw.text((x,10),f'{("BASELINE","STAGED CANDIDATE")[i]} | {slug} | {theme} | {width}px',fill='#111111');canvas.paste(im,(x,40))
    canvas.save(OUT/f'compare-{slug}-{theme}-{width}.png')
    rows.append({'slug':slug,'width':width,'theme':theme,'before':{k:a[k] for k in ('workloads','pihole','gateway')},'after':{k:b[k] for k in ('workloads','pihole','gateway')},'row_heights_before':[r['box']['height'] for r in a['rows']],'row_heights_after':[r['box']['height'] for r in b['rows']],'interactions':b.get('interactions')})
# All existing page sections outside Networking are byte-for-byte preserved.
config=ROOT/'tools/dynacat/config/dynacat.yml'
old=subprocess.check_output(['git','show','HEAD:tools/dynacat/config/dynacat.yml'],cwd=ROOT,text=True);new=config.read_text()
assert old.split('server:',1)[1].split('- name: NETWORKING')[0]==new.split('server:',1)[1].split('- name: NETWORKING')[0]
assert old.split('- name: MEDIA',1)[1]==new.split('- name: MEDIA',1)[1]
for name,digest in re.findall(r'/assets/([^?"<>]+)\?v=([a-f0-9]{12})',new.split('server:',1)[0]):
    assert hashlib.sha256((ROOT/'tools/dynacat/assets'/name).read_bytes()).hexdigest().startswith(digest),name
(OUT/'comparison-summary.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2));print('Scoped template preservation and asset hashes PASS')
