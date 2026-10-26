"""Offline browser acceptance for the centered, alphabetized endpoint launcher."""
import json
import os
import re
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright
import yaml

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from render_endpoints import render


def contrast_ratio(foreground, background):
    def luminance(color):
        channels = [int(component) / 255 for component in re.findall(r"\d+(?:\.\d+)?", color)[:3]]
        assert len(channels) == 3, color
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear))

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def verify():
    directory = json.loads((ROOT / "endpoints-directory.json").read_text())
    source = render(directory)
    config = yaml.safe_load((ROOT / "config/dynacat.yml").read_text())
    assert config["pages"][0].get("slug") == "endpoints-services", "The application launcher should be Dynacat's landing page"
    page_config = next(page for page in config["pages"] if page.get("slug") == "endpoints-services")
    assert page_config["columns"][0]["widgets"][0]["source"] == source, "Tracked page config must match the renderer"
    assert 'es-applications' in source and 'es-bookmarks' in source, "Renderer must emit the launchpad structure without JavaScript"
    assert source.index('es-applications') < source.index('es-bookmarks'), "Bookmarks must follow applications in source order"
    script = (ROOT / "assets/endpoints.js").read_text()
    styles = (ROOT / "assets/endpoint-directory.css").read_text()
    html = (
        "<!doctype html><html data-scheme='dark'><head><meta charset='utf-8'><style>"
        ":root{--color-background:#101318;--color-primary:#3b82c4;--color-text-highlight:#f1f1f1;"
        "--color-text-base:#bcbcbc;--color-text-subdue:#8c8c8c;--cc-border:rgba(255,255,255,.12)}"
        "body{margin:0;background:var(--color-background);color:var(--color-text-base);}"
        + styles
        + "</style></head><body>"
        + source
        + "<script>"
        + script
        + "</script></body></html>"
    )
    expected = [
        (item["name"], item["url"])
        for domain in directory["domains"]
        for group in domain["groups"]
        for item in group["links"]
    ]
    live_baseline = json.loads((ROOT / "fixtures/endpoints-before-rebuild.json").read_text())
    assert set(expected) == {(item["name"], item["url"]) for item in live_baseline}, "No existing endpoint URL or label may be changed"
    domain_counts = {
        domain["id"]: sum(len(group["links"]) for group in domain["groups"])
        for domain in directory["domains"]
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("DYNACAT_QA_CHROMIUM", "/usr/bin/chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(html)
        page.wait_for_function("document.querySelector('.es-directory-v2[data-ready=\"true\"]')")
        dark_theme = page.evaluate("""() => ({
            background:getComputedStyle(document.body).backgroundColor,
            accent:getComputedStyle(document.querySelector('.es-applications .es-endpoint strong')).color,
            description:getComputedStyle(document.querySelector('.es-applications .es-endpoint small')).color
        })""")
        dark_contrast = {
            "accent": contrast_ratio(dark_theme["accent"], dark_theme["background"]),
            "description": contrast_ratio(dark_theme["description"], dark_theme["background"]),
        }
        assert min(dark_contrast.values()) >= 4.5, (dark_theme, dark_contrast)

        pairs = page.locator(".es-endpoint").evaluate_all(
            "links => links.map(a => [a.querySelector('strong').textContent.trim(), a.getAttribute('href')])"
        )
        assert sorted(map(tuple, pairs)) == sorted(expected), "All existing endpoint labels and URLs must be preserved"
        assert page.locator(".es-applications .es-endpoint").count() == sum(
            count for key, count in domain_counts.items() if key != "personal"
        )
        assert page.locator(".es-bookmarks .es-endpoint").count() == domain_counts["personal"]
        assert page.locator(".es-applications").evaluate(
            "apps => Boolean(apps.compareDocumentPosition(document.querySelector('.es-bookmarks')) & Node.DOCUMENT_POSITION_FOLLOWING)"
        ), "Bookmarks must follow the applications grid"
        assert page.locator(".es-applications .es-endpoint strong").evaluate_all(
            "nodes => { const names = nodes.map(n => n.textContent.trim()); const c = new Intl.Collator(undefined, {sensitivity:'base', numeric:true}); return names.every((n,i) => i === 0 || c.compare(names[i-1], n) <= 0); }"
        ), "Applications must be alphabetized across service areas"

        page.locator('[data-es-category="media"]').click()
        assert page.locator(".es-endpoint:visible").count() == domain_counts["media"]
        assert page.locator(".es-applications").is_visible()
        assert not page.locator(".es-bookmarks").is_visible()
        page.locator('[data-es-category="personal"]').click()
        assert page.locator(".es-endpoint:visible").count() == domain_counts["personal"]
        assert not page.locator(".es-applications").is_visible()
        assert page.locator(".es-bookmarks").is_visible()
        page.locator('[data-es-category="all"]').click()
        page.locator("#endpoint-search").fill("backup tools")
        assert page.locator(".es-endpoint:visible strong").all_text_contents() == ["Backrest Tools"]
        page.locator("#endpoint-search").press("Escape")
        assert page.locator(".es-endpoint:visible").count() == len(expected)
        assert not errors, errors

        layouts = []
        for width, expected_columns in ((1600, 4), (900, 3), (700, 2), (390, 1)):
            page.set_viewport_size({"width": width, "height": 900})
            geometry = page.locator(".es-app-grid").evaluate(
                "grid => ({columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length, minHit:Math.min(...[...document.querySelectorAll('.es-endpoint')].map(a=>a.getBoundingClientRect().height)), minCategoryHit:Math.min(...[...document.querySelectorAll('.es-categories button')].map(button=>button.getBoundingClientRect().height)), scrollWidth:document.documentElement.scrollWidth})"
            )
            assert geometry["columns"] == expected_columns, (width, geometry)
            assert geometry["minHit"] >= 44, (width, geometry)
            assert geometry["minCategoryHit"] >= 44, (width, geometry)
            assert geometry["scrollWidth"] <= width, (width, geometry)
            layouts.append({"width": width, **geometry})

        assert page.locator(".es-applications .es-endpoint strong").first.evaluate(
            "el => getComputedStyle(el).color"
        ) == "rgb(255, 96, 64)", "The dark launchpad should retain the Flame coral accent"
        light_theme = page.evaluate("""() => {
            const root=document.documentElement;
            root.dataset.scheme='light';
            for (const [key,value] of Object.entries({'--color-background':'#ffffff','--color-primary':'#223344','--color-text-highlight':'#171717','--color-text-base':'#333333','--color-text-subdue':'#555555','--cc-border':'#cccccc'})) root.style.setProperty(key,value);
            return {
                background:getComputedStyle(document.body).backgroundColor,
                title:getComputedStyle(document.querySelector('.es-applications .es-endpoint strong')).color,
                description:getComputedStyle(document.querySelector('.es-applications .es-endpoint small')).color,
                bookmark:getComputedStyle(document.querySelector('.es-bookmarks .es-endpoint strong')).color
            };
        }""")
        assert light_theme["background"] == "rgb(255, 255, 255)", light_theme
        assert light_theme["title"] == "rgb(34, 51, 68)", light_theme
        assert light_theme["bookmark"] == "rgb(23, 23, 23)", light_theme
        light_contrast = {
            "accent": contrast_ratio(light_theme["title"], light_theme["background"]),
            "description": contrast_ratio(light_theme["description"], light_theme["background"]),
            "bookmark": contrast_ratio(light_theme["bookmark"], light_theme["background"]),
        }
        assert min(light_contrast.values()) >= 4.5, (light_theme, light_contrast)

        late_page = browser.new_page()
        late_page.on("pageerror", lambda error: errors.append(str(error)))
        late_page.route(
            "http://dynacat.test/**",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body=f"<html><body><script>{script}</script>{source}</body></html>",
            ),
        )
        late_page.goto("http://dynacat.test/")
        late_page.wait_for_selector('.es-directory-v2[data-ready="true"]', timeout=1500)
        assert late_page.locator(".es-endpoint").count() == len(expected)
        late_page.close()
        assert not errors, errors
        browser.close()
    print(
        json.dumps(
            {
                "links_preserved": len(expected),
                "applications": sum(count for key, count in domain_counts.items() if key != "personal"),
                "bookmarks": domain_counts["personal"],
                "alphabetical": True,
                "search_and_filters": True,
                "responsive_layouts": layouts,
                "theme_contrast": {"dark": dark_contrast, "light": light_contrast},
                "page_errors": errors,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    verify()
