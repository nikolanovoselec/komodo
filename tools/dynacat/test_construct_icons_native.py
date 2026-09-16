"""Opt-in isolated native renderer (no production connection or deployment).
RUN_CONSTRUCT_ICON_NATIVE=1 pytest -q tools/dynacat/test_construct_icons_native.py
Requires Docker with the already-present panonim/dynacat:3.0.0 image.
"""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen
from urllib.parse import urljoin

import pytest
import yaml

ROOT = Path(__file__).parent


@pytest.mark.skipif(os.environ.get('RUN_CONSTRUCT_ICON_NATIVE') != '1', reason='isolated Docker renderer opt-in')
def test_native_html_manifest_and_served_icon_bytes():
    config = yaml.safe_load((ROOT / 'config/dynacat.yml').read_text())
    # Retain production branding and document head, but never poll production APIs.
    config['server'] = {'port': 8080, 'assets-path': '/app/assets', 'cache-dir': '/tmp/cache'}
    config['pages'] = [{'name': 'Icon QA', 'slug': 'icon-qa', 'columns': [{'size': 'full', 'widgets': [{'type': 'html', 'source': '<p>Native icon verification</p>'}]}]}]
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []
        def handle_starttag(self, tag, attrs):
            if tag == 'link':
                self.links.append(dict(attrs))
    container = None
    with tempfile.TemporaryDirectory(prefix='.icon-native-', dir=ROOT) as temp:
        Path(temp, 'dynacat.yml').write_text(yaml.safe_dump(config, sort_keys=False))
        try:
            container = subprocess.check_output([
                'docker', 'run', '-d', '--pull=never', '--read-only', '--tmpfs', '/tmp',
                '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '-p', '127.0.0.1::8080',
                '-v', f'{temp}:/app/config:ro', '-v', f'{ROOT / "assets"}:/app/assets:ro',
                'panonim/dynacat:3.0.0'], text=True).strip()
            address = subprocess.check_output(['docker', 'port', container, '8080'], text=True).strip()
            base = 'http://' + address
            html = ''
            for attempt in range(50):
                try:
                    with urlopen(base + '/icon-qa', timeout=2) as response:
                        html = response.read().decode()
                    break
                except OSError:
                    if attempt == 49:
                        print(subprocess.check_output(['docker', 'logs', container], text=True))
                        raise
                    time.sleep(.1)
            links = Links()
            links.feed(html)
            icon = [x for x in links.links if x.get('rel') in ('icon', 'shortcut icon')]
            touch = [x for x in links.links if x.get('rel') == 'apple-touch-icon']
            manifests = [x for x in links.links if x.get('rel') == 'manifest']
            assert len(icon) == len(touch) == len(manifests) == 1
            assert icon[0]['href'] == config['branding']['favicon-url']
            assert icon[0]['type'] == 'image/png'
            assert touch[0]['href'] == config['branding']['app-icon-url']
            assert touch[0]['sizes'] == '512x512'
            with urlopen(urljoin(base + '/icon-qa', manifests[0]['href'])) as response:
                manifest = json.load(response)
            assert manifest['icons'] == [{'src': config['branding']['app-icon-url'], 'type': 'image/png', 'sizes': '512x512'}]
            assert manifest['background_color'] == '#1b1f26'
            assert manifest['theme_color'] == '#1b1f26'
            for link, size in [(icon[0], 32), (touch[0], 512)]:
                with urlopen(base + link['href']) as response:
                    assert response.status == 200
                    assert response.headers.get_content_type() == 'image/png'
                    data = response.read()
                expected = (ROOT / f'assets/construct-icons/icon-{size}.png').read_bytes()
                assert data == expected
                assert hashlib.sha256(data).hexdigest()[:12] in link['href']
            print(json.dumps({'native_image': 'panonim/dynacat:3.0.0', 'icon_links': icon, 'touch_links': touch, 'manifest': manifest, 'served_bytes_match': True}))
        finally:
            if container:
                subprocess.run(['docker', 'rm', '-f', container], check=True, capture_output=True)
