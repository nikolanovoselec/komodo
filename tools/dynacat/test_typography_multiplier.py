"""Regression contracts for Dynacat's centrally controlled typography scale."""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).parent
CONFIG = ROOT / "config" / "dynacat.yml"
ASSETS = ROOT / "assets"
PX_DECL = re.compile(r"(?P<property>font-size|line-height)\s*:\s*(?P<value>\d+(?:\.\d+)?)px\b")
ASSET_REF = re.compile(r"/assets/([^?\"']+\.css)(?:\?[^\"']*)?")


def referenced_css_assets():
    names = sorted(set(ASSET_REF.findall(CONFIG.read_text())))
    assert names, "config must reference CSS assets"
    return [ASSETS / name for name in names]


def test_command_center_defines_the_single_central_multiplier():
    text = (ASSETS / "command-center.css").read_text()
    assert text.count("--cc-type-scale:") == 1
    assert "--cc-type-scale:1.4" in text
    assert "/* Central typography control:" in text


def test_all_referenced_css_text_sizes_use_the_central_multiplier():
    failures = []
    for path in referenced_css_assets():
        for match in PX_DECL.finditer(path.read_text()):
            failures.append(f"{path.name}: {match.group(0)}")
    assert not failures, "unscaled scoped text declarations:\n" + "\n".join(failures)


def test_referenced_assets_exist_and_config_uses_current_hashes():
    config_text = CONFIG.read_text()
    for path in referenced_css_assets():
        assert path.exists(), path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        assert f"/assets/{path.name}?v={digest}" in config_text, path.name


def test_no_page_zoom_or_transform_typography_hacks():
    for path in referenced_css_assets():
        text = path.read_text()
        assert not re.search(r"(?:html|body)[^{]*\{[^}]*\bzoom\s*:", text), path.name
        assert not re.search(r"(?:html|body)[^{]*\{[^}]*transform\s*:", text), path.name
