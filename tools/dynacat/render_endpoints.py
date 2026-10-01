"""Render explicit purpose groups into the existing native HTML widget only."""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
import yaml

ROOT = Path(__file__).parent

def render(directory):
    escape = lambda value: html.escape(str(value), quote=True)
    domains = directory['domains']
    total = sum(len(group['links']) for domain in domains for group in domain['groups'])
    bits = [f'<section class="es-launcher es-directory-v2" aria-label="Service directory">',
      '<header class="es-heading"><div><h2>Endpoints &amp; Services</h2><p>Find a service by what it does.</p></div>',
      f'<span class="es-inventory-label">{total} links · grouped by purpose</span></header>',
      '<div class="es-toolbar"><div class="es-search-row"><label for="endpoint-search">Find a service</label>',
      '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>',
      '<input id="endpoint-search" type="search" placeholder="Search by name, purpose or address" autocomplete="off" spellcheck="false">',
      '<button type="button" class="es-clear" aria-label="Clear search" hidden>Clear</button></div>',
      '<nav class="es-categories" aria-label="Service areas">',
      '<button type="button" data-es-category="all" aria-pressed="true">All</button>']
    for domain in domains:
        count = sum(len(g['links']) for g in domain['groups'])
        bits.append(f'<button type="button" data-es-category="{escape(domain["id"])}" aria-pressed="false">{escape(domain["title"])}<span>{count}</span></button>')
    bits.extend(['</nav></div>',f'<div class="es-results-line"><span class="es-result-count" aria-live="polite">{total} links</span><span>Alphabetical within each group</span></div>'])
    for domain in domains:
        count = sum(len(g['links']) for g in domain['groups'])
        bits.append(f'<section class="es-domain" data-es-domain="{escape(domain["id"])}" aria-labelledby="es-domain-{escape(domain["id"])}">')
        bits.append(f'<header class="es-domain-header"><h3 id="es-domain-{escape(domain["id"])}">{escape(domain["title"])}</h3><p>{escape(domain["description"])}</p><span class="es-domain-count">{count}</span></header>')
        bits.append('<div class="es-group-grid">')
        for group in domain['groups']:
            bits.append(f'<section class="es-group" data-es-group="{escape(group["id"])}" data-es-domain-key="{escape(domain["id"])}" aria-labelledby="es-group-{escape(group["id"])}">')
            bits.append(f'<h4 id="es-group-{escape(group["id"])}">{escape(group["title"])}<span class="es-group-count">{len(group["links"])}</span></h4><ul class="es-grid">')
            for item in group['links']:
                name, url, desc = item['name'], item['url'], item['description']
                parsed = urlsplit(url)
                if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError('Unsafe directory URL')
                search = ' '.join([name,url,desc,group['title'],domain['title']])
                bits.append(f'<li><a class="es-endpoint" href="{escape(url)}" rel="noopener noreferrer" data-es-search="{escape(search)}" title="{escape(url)}"><span class="es-link-copy"><strong>{escape(name)}</strong><small>{escape(desc)}</small></span><span class="es-open" aria-hidden="true">↗</span></a></li>')
            bits.extend(['</ul></section>'])
        bits.append('</div></section>')
    bits.extend(['<div class="es-empty" hidden><strong>No matching service</strong><p>Try a name, purpose or hostname, or select All.</p></div>', '</section>'])
    return ''.join(bits)

def main():
    path = ROOT/'config/dynacat.yml'
    original = path.read_text()
    config = yaml.safe_load(original)
    page = next(p for p in config['pages'] if p.get('slug')=='endpoints-services')
    widget = page['columns'][0]['widgets'][0]
    previous = widget['source']
    result = render(json.loads((ROOT/'endpoints-directory.json').read_text()))
    # Preserve every unrelated YAML byte, including quoted prior generated content.
    start = original.index('- name: ENDPOINTS & SERVICES\n')
    end = original.index('\n- name:', start + 1)
    section = original[start:end]
    replacement, count = re.subn(r'^      source: .*$', lambda _: '      source: '+json.dumps(result, ensure_ascii=False), section, count=1, flags=re.M)
    assert count==1, 'Launcher source changed; re-evaluate patch boundary'
    changed = original[:start]+replacement+original[end:]
    changed = changed.replace('/assets/endpoints.css?v=', '/assets/endpoint-directory.css?v=')
    for name in ('endpoint-directory.css','endpoints.js'):
        digest=hashlib.sha256((ROOT/'assets'/name).read_bytes()).hexdigest()[:12]
        changed=re.sub(r'(/assets/'+re.escape(name)+r'\?v=)[a-zA-Z0-9_-]+',lambda m:m[1]+digest,changed)
    verified=yaml.safe_load(changed)
    newpage=next(p for p in verified['pages'] if p.get('slug')=='endpoints-services')
    assert newpage['columns'][0]['widgets'][0]['source']==result
    path.write_text(changed)
    print('Native launcher source rendered; unrelated configuration preserved.')

if __name__=='__main__': main()
