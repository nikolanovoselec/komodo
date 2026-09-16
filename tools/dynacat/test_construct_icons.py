"""Vendored user artwork: exact provenance, aspect-preserving pixels and native wiring."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from PIL import Image, ImageChops
import yaml

ROOT = Path(__file__).parent
ICONS = ROOT / 'assets/construct-icons'
SOURCE_SHA256 = 'c0bdd6ac38f6180e1da06ec28f49b322af5ab26f36c66699641765378cb8eec1'


def test_vendored_source_and_square_derivatives():
    source = ICONS / 'source-rRziaa.png'
    assert source.exists(), 'Vendor the original user PNG without modifying its bytes'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    original = Image.open(source).convert('RGB')
    assert original.size == (869, 755)
    # Source top-left navy; center the FULL 869x755 image on 869x869,
    # then uniformly resample. Exact comparison catches crop/stretch/transparency.
    square = Image.new('RGB', (869, 869), original.getpixel((0, 0)))
    square.paste(original, (0, 57))
    for size in (32, 512):
        path = ICONS / f'icon-{size}.png'
        assert path.exists()
        actual = Image.open(path)
        assert actual.format == 'PNG'
        assert actual.mode == 'RGB'
        assert actual.size == (size, size)
        expected = square.resize((size, size), Image.Resampling.LANCZOS)
        assert ImageChops.difference(actual, expected).getbbox() is None
    provenance = json.loads((ICONS / 'provenance.json').read_text())
    assert provenance['source_sha256'] == SOURCE_SHA256
    assert provenance['padding_rgb'] == [27, 31, 38]
    assert provenance['source_offset'] == [0, 57]
    assert provenance['generated_sizes'] == [32, 512]


def test_native_branding_wiring_is_local_content_versioned():
    config = yaml.safe_load((ROOT / 'config/dynacat.yml').read_text())
    for key, size in [('favicon-url', 32), ('app-icon-url', 512)]:
        assert key in config['branding'], f'Missing native {key}; do not append a competing icon link'
        url = urlsplit(config['branding'][key])
        assert not url.netloc and not url.scheme
        assert url.path == f'/assets/construct-icons/icon-{size}.png'
        data = (ROOT / url.path.lstrip('/')).read_bytes()
        assert parse_qs(url.query) == {'v': [hashlib.sha256(data).hexdigest()[:12]]}
    assert config['branding']['app-background-color'] == '#1b1f26'
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'link':
                assert dict(attrs).get('rel') not in ('icon', 'shortcut icon', 'apple-touch-icon', 'manifest'), 'Native template already emits these links'
    Links().feed(config['document']['head'])
