from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "tools/dynacat/config/dynacat.yml"

EXPECTED = {
    "nord", "tokyo-night", "one-dark", "solarized-dark", "solarized-light",
    "monokai", "rose-pine", "rose-pine-moon", "everforest-dark", "everforest-light",
    "gruvbox-light", "tokyo-night-storm", "dracula-soft", "material-ocean",
    "ayu-dark", "ayu-light", "github-light", "github-dark", "synthwave-84", "horizon",
}


def load_config():
    return yaml.safe_load(CONFIG.read_text())


def test_twenty_new_theme_keys_are_present():
    presets = load_config()["theme"]["presets"]
    assert EXPECTED <= set(presets)
    assert len(EXPECTED) == 20


def test_new_theme_keys_are_unique_and_have_complete_palette():
    presets = load_config()["theme"]["presets"]
    assert len(presets) == 40  # 20 existing presets + 20 new presets; default-dark/light are generated
    required = {"background-color", "primary-color", "positive-color", "negative-color"}
    for key in EXPECTED:
        assert required <= set(presets[key]), key
        assert len(set(presets[key]) & {"background-color", "primary-color", "positive-color", "negative-color"}) == 4


def test_oled_high_contrast_uses_exact_bright_orange_primary_on_black():
    oled = load_config()["theme"]["presets"]["oled-high-contrast"]
    assert oled["background-color"] == "0 0 0"
    assert oled["primary-color"] == "28 100 65"
    assert oled["positive-color"] == "145 78 62"
    assert oled["negative-color"] == "4 90 67"


def test_picker_is_bounded_and_scrollable():
    css = (ROOT / "tools/dynacat/assets/command-center.css").read_text()
    assert ".theme-picker" in css
    assert "overflow-y:auto" in css
    assert "max-height" in css
    assert ".theme-choices{max-height" in css
    assert "ch.graymatter.config-revision: \"themes-23-oled-orange\"" in (ROOT / "tools/dynacat/compose.yaml").read_text()
