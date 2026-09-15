"""Prepare isolated local compact-session QA from a real read-only capture."""
import copy,json,shutil,sys
from pathlib import Path
import yaml
root=Path(__file__).parent
out=Path(sys.argv[1]);variant=sys.argv[2];out.mkdir(parents=True,exist_ok=True)
config=yaml.safe_load((root/'config/dynacat.yml').read_text())
media=next(p for p in config['pages'] if p.get('slug')=='media' or p['name']=='Media')
widget=next(w for c in media['columns'] for w in c['widgets'] if 'mo-live' in w.get('template',''))
widget=copy.deepcopy(widget);widget['url']='http://media-compact-source:8090/media-current';widget['cache']='1h'
# Session-only staged view uses the real template and real layout/theme rules.
t=widget['template'];start=t.index('<div class="mo-section"><h3>Now playing');end=t.index('<div class="mo-section"><h3>Media servers')
widget['template']='<div class="mo-page mo-live"><p>STAGED READ-ONLY CAPTURE · two actual Plex sessions · not live playback controls</p>'+t[start:end].removesuffix('{{ end }}')+'</div>'
# Closing end belongs to sessions.error conditional before the selected section.
widget['template']=widget['template'].replace('</div>{{ end }}\n','</div>\n')
config['pages']=[dict(name='Media',slug='media',columns=[dict(size='full',widgets=[widget])])]
config['document']['head']='<link rel="stylesheet" href="/assets/media-ops.css">'
config['server']['port']=8080
config['server']['cache-dir']='/tmp/cache'
config['theme'].pop('custom-css-file',None)
(out/variant/'config').mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'assets',out/variant/'assets',dirs_exist_ok=True)
(out/variant/'config/dynacat.yml').write_text(yaml.safe_dump(config,sort_keys=False))
(out/'source').mkdir(exist_ok=True)
shutil.copyfile('/tmp/media-compact-source.json',out/'source/media-current')
print(out/variant)
