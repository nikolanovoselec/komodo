"""Offline browser acceptance for the Flame-style MDI launcher."""
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
    icon_doc = json.loads((ROOT / "flame-mdi-icons.json").read_text())
    source = render(directory)
    config = yaml.safe_load((ROOT / "config/dynacat.yml").read_text())
    assert config["pages"][0].get("slug") == "endpoints-services", "Launcher must remain Dynacat's landing page"
    page_config = next(page for page in config["pages"] if page.get("slug") == "endpoints-services")
    assert page_config["columns"][0]["widgets"][0]["source"] == source, "Tracked widget must match the renderer"
    assert "es-applications" in source and "es-bookmarks" in source
    assert source.index("es-applications") < source.index("es-bookmarks"), "Bookmarks must follow applications"

    script = (ROOT / "assets/endpoints.js").read_text()
    styles = (ROOT / "assets/endpoint-directory.css").read_text()
    html = (
        "<!doctype html><html data-scheme='dark'><head><meta charset='utf-8'><style>"
        ":root{--color-background:#101318;--color-primary:#3b82c4;--color-text-highlight:#f1f1f1;"
        "--color-text-base:#bcbcbc;--color-text-subdue:#8c8c8c;--cc-border:rgba(255,255,255,.12)}"
        "body{margin:0;min-height:100vh;background:var(--color-background);color:var(--color-text-base);}"
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
    baseline = json.loads((ROOT / "fixtures/endpoints-before-rebuild.json").read_text())
    assert set(expected) == {(item["name"], item["url"]) for item in baseline}, "Every original label and URL must be preserved"
    app_count = sum(len(group["links"]) for domain in directory["domains"] if domain["id"] != "personal" for group in domain["groups"])
    bookmark_count = sum(len(group["links"]) for domain in directory["domains"] if domain["id"] == "personal" for group in domain["groups"])
    assert len(expected) == 77 and app_count == 52 and bookmark_count == 25
    expected_bookmark_groups = [
        ("news", "News", 7),
        ("productivity-multimedia", "Productivity & Multimedia", 8),
        ("shopping", "Shopping", 4),
        ("utilities", "Utilities", 6),
    ]
    bookmark_domain = next(domain for domain in directory["domains"] if domain["id"] == "personal")
    actual_bookmark_groups = [
        (group["id"], group["title"], len(group["links"]))
        for group in bookmark_domain["groups"]
    ]
    assert actual_bookmark_groups == expected_bookmark_groups, actual_bookmark_groups

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("DYNACAT_QA_CHROMIUM", "/usr/bin/chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(html)
        page.wait_for_selector('.es-directory-v2[data-ready="true"]')

        pairs = page.locator(".es-endpoint").evaluate_all(
            "links => links.map(a => [a.querySelector('strong').textContent.trim(), a.getAttribute('href')])"
        )
        assert sorted(map(tuple, pairs)) == sorted(expected), "All original labels and URLs must remain"
        assert page.locator(".es-applications .es-endpoint").count() == app_count
        assert page.locator(".es-bookmarks .es-endpoint").count() == bookmark_count
        assert page.locator(".es-applications .es-endpoint strong").evaluate_all(
            "nodes => { const names = nodes.map(n => n.textContent.trim()); const c = new Intl.Collator(undefined, {sensitivity:'base', numeric:true}); return names.every((n,i) => i === 0 || c.compare(names[i-1], n) <= 0); }"
        ), "Applications must be alphabetized across service areas"
        assert page.locator(".es-applications").evaluate(
            "apps => Boolean(apps.compareDocumentPosition(document.querySelector('.es-bookmarks')) & Node.DOCUMENT_POSITION_FOLLOWING)"
        ), "Bookmarks must follow the application grid"
        assert page.locator(".es-toolbar, .es-search-row, .es-categories").count() == 0, "The Flame-style page should stay uncluttered"

        icon_report = page.evaluate("""() => ({
            symbols:[...document.querySelectorAll('.es-icon-sprite symbol')].map(s=>s.id).sort(),
            references:[...document.querySelectorAll('.es-endpoint')].map(a=>({
                name:a.querySelector('strong').textContent.trim(),
                id:a.dataset.esIcon,
                href:a.querySelector('.es-icon use')?.getAttribute('href'),
                iconWidth:a.querySelector('.es-icon')?.getBoundingClientRect().width
            }))
        })""")
        expected_symbols = sorted(f"es-mdi-{name}" for name in icon_doc["icons"])
        assert icon_report["symbols"] == expected_symbols
        for ref in icon_report["references"]:
            assert ref["href"] == f"#es-mdi-{ref['id']}", ref
        assert len(icon_report["references"]) == len(expected)

        layouts = []
        for width in (1600, 1100, 900, 899, 700, 670, 669, 430, 429, 390):
            page.set_viewport_size({"width": width, "height": 900})
            geometry = page.evaluate("""() => {
                const root=document.querySelector('.es-directory-v2');
                const links=[...root.querySelectorAll('.es-endpoint')];
                const appGrid=root.querySelector('.es-app-grid');
                const appLinks=[...root.querySelectorAll('.es-applications .es-endpoint')];
                const bookmarkLinks=[...root.querySelectorAll('.es-bookmarks .es-endpoint')];
                const appColumns=getComputedStyle(appGrid).gridTemplateColumns.split(' ').length;
                const bg=getComputedStyle(document.body).backgroundColor;
                const title=getComputedStyle(root.querySelector('.es-applications .es-endpoint strong')).color;
                const desc=getComputedStyle(root.querySelector('.es-applications .es-endpoint small')).color;
                const bookmark=getComputedStyle(root.querySelector('.es-bookmarks .es-endpoint strong')).color;
                return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                    appColumns:getComputedStyle(appGrid).gridTemplateColumns.split(' ').length,
                    bookmarkColumns:getComputedStyle(root.querySelector('.es-group-grid')).gridTemplateColumns.split(' ').length,
                    containerWidth:root.getBoundingClientRect().width,
                    containerLeft:root.getBoundingClientRect().left,
                    parentWidth:root.parentElement.getBoundingClientRect().width,
                    parentLeft:root.parentElement.getBoundingClientRect().left,
                    paddingLeft:parseFloat(getComputedStyle(root).paddingLeft),
                    appIconWidth:root.querySelector('.es-applications .es-icon').getBoundingClientRect().width,
                    bookmarkIconWidth:root.querySelector('.es-bookmarks .es-icon').getBoundingClientRect().width,
                    appColumnGap:getComputedStyle(appGrid).columnGap,
                    bookmarkColumnGap:getComputedStyle(root.querySelector('.es-group-grid')).columnGap,
                    descriptionSize:getComputedStyle(root.querySelector('.es-applications small')).fontSize,
                    appMarginBottom:parseFloat(getComputedStyle(appLinks[0]).marginBottom),
                    appRowPitch:appLinks[appColumns].getBoundingClientRect().top-appLinks[0].getBoundingClientRect().top,
                    appMinHit:Math.min(...appLinks.map(a=>a.getBoundingClientRect().height)),
                    bookmarkFontSize:getComputedStyle(bookmarkLinks[0].querySelector('strong')).fontSize,
                    bookmarkLineHeight:getComputedStyle(bookmarkLinks[0].querySelector('strong')).lineHeight,
                    bookmarkGap:getComputedStyle(bookmarkLinks[0]).gap,
                    bookmarkRowPitch:bookmarkLinks[1].getBoundingClientRect().top-bookmarkLinks[0].getBoundingClientRect().top,
                    bookmarkMinHit:Math.min(...bookmarkLinks.map(a=>a.getBoundingClientRect().height)),
                    minHit:Math.min(...links.map(a=>a.getBoundingClientRect().height)),
                    background:bg,title,description:desc,bookmark};
            }""")
            expected_columns = 4 if width >= 900 else 3 if width >= 670 else 2 if width >= 430 else 1
            parent_width = geometry["parentWidth"]
            if width < 769:
                expected_container_width, expected_padding = parent_width, 20
            elif width < 1201:
                expected_container_width, expected_padding = parent_width * 0.9, 20
            else:
                expected_container_width, expected_padding = min(parent_width * 0.9, 1714), 250
            expected_description_size = "10px" if 430 <= width <= 480 else "11px"
            assert geometry["scrollWidth"] <= width, geometry
            assert geometry["appColumns"] == expected_columns, geometry
            assert geometry["bookmarkColumns"] == expected_columns, geometry
            assert abs(geometry["containerWidth"] - expected_container_width) < 1, geometry
            assert abs((geometry["containerLeft"] - geometry["parentLeft"]) - (parent_width - geometry["containerWidth"]) / 2) < 1, geometry
            assert abs(geometry["paddingLeft"] - expected_padding) < 1, geometry
            assert geometry["appIconWidth"] == 35, geometry
            assert geometry["bookmarkIconWidth"] == 20, geometry
            assert geometry["appColumnGap"] == "0px", geometry
            assert geometry["bookmarkColumnGap"] == "0px", geometry
            assert geometry["descriptionSize"] == expected_description_size, geometry
            assert geometry["appMarginBottom"] == 14, geometry
            # Chromium can report 58.99997px for Flame's nominal 59px pitch.
            assert geometry["appRowPitch"] >= 58.9, geometry
            assert geometry["appMinHit"] >= 44, geometry
            assert geometry["bookmarkFontSize"] == "14px", geometry
            assert geometry["bookmarkLineHeight"] == "28px", geometry
            assert geometry["bookmarkGap"] == "2px", geometry
            expected_bookmark_height = 45 if width <= 760 else 28
            assert abs(geometry["bookmarkRowPitch"] - expected_bookmark_height) < 0.1, geometry
            # Browser fractional layout can shave a tiny amount off a 45px hit box.
            assert geometry["bookmarkMinHit"] >= expected_bookmark_height - 0.1, geometry
            layouts.append({"width": width, **geometry})

        dark_theme = layouts[0]
        dark_contrast = {
            "appAccent": contrast_ratio(dark_theme["title"], dark_theme["background"]),
            "description": contrast_ratio(dark_theme["description"], dark_theme["background"]),
            "bookmark": contrast_ratio(dark_theme["bookmark"], dark_theme["background"]),
        }
        assert min(dark_contrast.values()) >= 4.5, (dark_theme, dark_contrast)

        light_theme = page.evaluate("""() => {
            const root=document.documentElement;
            root.dataset.scheme='light';
            for (const [key,value] of Object.entries({'--color-background':'#eff1f5','--color-primary':'#1e66f5','--color-text-highlight':'#4c4f69','--color-text-base':'#5c5f77','--color-text-subdue':'#6c6f85','--cc-border':'#ccd0da'})) root.style.setProperty(key,value);
            document.body.style.background='var(--color-background)';
            const launcher=document.querySelector('.es-directory-v2');
            return {background:getComputedStyle(document.body).backgroundColor,
                title:getComputedStyle(launcher.querySelector('.es-applications .es-endpoint strong')).color,
                description:getComputedStyle(launcher.querySelector('.es-applications .es-endpoint small')).color,
                bookmark:getComputedStyle(launcher.querySelector('.es-bookmarks .es-endpoint strong')).color};
        }""")
        light_contrast = {
            "appAccent": contrast_ratio(light_theme["title"], light_theme["background"]),
            "description": contrast_ratio(light_theme["description"], light_theme["background"]),
            "bookmark": contrast_ratio(light_theme["bookmark"], light_theme["background"]),
        }
        assert min(light_contrast.values()) >= 4.5, (light_theme, light_contrast)

        screenshot_path = os.environ.get("DYNACAT_QA_SCREENSHOT")
        if screenshot_path:
            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
            page.evaluate("""() => {
                const root=document.documentElement;
                root.dataset.scheme='dark';
                for (const key of ['--color-background','--color-primary','--color-text-highlight','--color-text-base','--color-text-subdue','--cc-border']) root.style.removeProperty(key);
                document.body.style.removeProperty('background');
            }""")
            page.set_viewport_size({"width": 1714, "height": 1100})
            page.screenshot(path=screenshot_path, full_page=True)

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

    print(json.dumps({
        "links_preserved": len(expected),
        "applications": app_count,
        "bookmarks": bookmark_count,
        "flame_mdi_icons": len(icon_doc["icons"]),
        "alphabetical": True,
        "search_and_filter_chrome": False,
        "responsive_layouts": layouts,
        "theme_contrast": {"dark": dark_contrast, "light": light_contrast},
        "page_errors": errors,
        "screenshot": screenshot_path or None,
    }, indent=2))


if __name__ == "__main__":
    verify()
