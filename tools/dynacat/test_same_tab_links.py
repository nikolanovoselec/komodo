from pathlib import Path


ROOT = Path(__file__).parent


def test_dashboard_custom_templates_do_not_request_new_tabs():
    source = (ROOT / "config" / "dynacat.yml").read_text()
    assert 'target="_blank"' not in source
    assert "target='_blank'" not in source


def test_dashboard_assets_do_not_open_ordinary_links_in_new_windows():
    for path in (ROOT / "assets").glob("*.js"):
        if path.name.endswith(".test.cjs") or path.name == "same-tab-links.js":
            continue
        assert "window.open" not in path.read_text(), path


def test_same_tab_runtime_guard_is_loaded_with_a_content_hash():
    config = (ROOT / "config" / "dynacat.yml").read_text()
    asset = ROOT / "assets" / "same-tab-links.js"
    assert asset.exists()
    assert "same-tab-links.js?v=" in config
    source = asset.read_text()
    assert "removeAttribute('target')" in source
    assert "location.assign" in source
