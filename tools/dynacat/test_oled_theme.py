from pathlib import Path

import yaml


CONFIG = Path(__file__).parent / "config" / "dynacat.yml"
REQUIRED = {
    "background-color",
    "primary-color",
    "positive-color",
    "negative-color",
    "contrast-multiplier",
    "light",
}


def oled_theme():
    config = yaml.safe_load(CONFIG.read_text())
    return config["theme"]["presets"]["oled-high-contrast"]


def hsl(value):
    return tuple(int(part) for part in value.split())


def test_oled_high_contrast_is_registered_with_complete_black_palette():
    theme = oled_theme()
    assert set(theme) >= REQUIRED
    assert theme["light"] is False
    assert hsl(theme["background-color"]) == (0, 0, 0)
    assert theme["contrast-multiplier"] >= 1.25


def test_oled_high_contrast_uses_bright_distinct_semantic_colors():
    theme = oled_theme()
    primary = hsl(theme["primary-color"])
    positive = hsl(theme["positive-color"])
    negative = hsl(theme["negative-color"])
    assert primary[2] >= 65
    assert positive[2] >= 55
    assert negative[2] >= 55
    assert len({primary, positive, negative}) == 3


def test_oled_high_contrast_primary_is_accessible_orange():
    primary = hsl(oled_theme()["primary-color"])
    assert 20 <= primary[0] <= 35
    assert primary[1] >= 90
    assert primary[2] >= 60


def test_oled_high_contrast_scopes_an_accessible_amber_warning_token():
    css = (CONFIG.parent.parent / "assets" / "command-center.css").read_text()
    assert 'data-theme="oled-high-contrast"' in css
    assert "#ffd166" in css