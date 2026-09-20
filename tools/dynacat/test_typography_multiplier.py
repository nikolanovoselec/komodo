"""Contracts for the centrally controlled Dynacat typography scale."""
from pathlib import Path
import re

CSS = Path(__file__).parent / "assets" / "command-center.css"


def test_command_center_has_single_documented_default_type_scale():
    text = CSS.read_text()
    assert text.count("--cc-type-scale:") == 1
    assert "--cc-type-scale:1.4" in text
    assert "/* Central typography control:" in text


def test_representative_small_dashboard_sizes_use_the_multiplier():
    text = CSS.read_text()
    for size in ("9px", "10px", "11px", "12px", "13px"):
        assert f"calc(var(--cc-type-scale) * {size})" in text


def test_scoped_small_fixed_font_sizes_are_not_unscaled():
    text = CSS.read_text()
    unscaled = re.findall(r"font-size\s*:\s*(?:[89]|1[0-3])px\b", text)
    assert not unscaled, f"unscaled command-center sizes: {unscaled}"
