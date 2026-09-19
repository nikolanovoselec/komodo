from pathlib import Path


ROOT = Path(__file__).parent


def test_dashboard_custom_templates_do_not_request_new_tabs():
    source = (ROOT / "config" / "dynacat.yml").read_text()
    assert 'target="_blank"' not in source
    assert "target='_blank'" not in source


def test_dashboard_assets_do_not_open_ordinary_links_in_new_windows():
    for path in (ROOT / "assets").glob("*.js"):
        if path.name.endswith(".test.cjs"):
            continue
        assert "window.open" not in path.read_text(), path
