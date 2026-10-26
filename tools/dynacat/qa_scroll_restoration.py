"""Regression check for scroll restoration after same-tab launcher links."""
import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.environ.get("DYNACAT_QA_BASE", "http://192.168.2.72:8080").rstrip("/")
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_same_tab_links_asset(staged):
    if staged:
        return subprocess.check_output(
            ["git", "show", ":tools/dynacat/assets/same-tab-links.js"],
            cwd=REPO_ROOT,
            text=True,
        )
    return (Path(__file__).parent / "assets" / "same-tab-links.js").read_text()


async def verify_device(playwright, label, viewport, mobile=False, staged=False):
    browser = await playwright.chromium.launch()
    page = await browser.new_page(viewport=viewport, is_mobile=mobile, has_touch=mobile)
    if staged:
        source = load_same_tab_links_asset(staged)

        async def serve_staged_asset(route):
            await route.fulfill(status=200, content_type="application/javascript", body=source)

        await page.route("**/assets/same-tab-links.js*", serve_staged_asset)

    async def serve_external_destination(route):
        await route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>Scroll QA destination</title>")

    await page.route("https://dynacat-scroll-test.invalid/**", serve_external_destination)
    await page.add_init_script("""
        document.addEventListener('click', event => {
            const link = event.target.closest?.('a[href]');
            if (link?.textContent.trim() === 'YouTube') {
                sessionStorage.setItem('__dynacat_scroll_test_clicked_y', String(window.scrollY));
            }
        }, true);
    """)

    await page.goto(f"{BASE}/endpoints-services", wait_until="load")
    await page.wait_for_function("Array.from(document.querySelectorAll('a')).some(a => a.textContent.trim() === 'YouTube')")
    test_history_state = 17 if label == "desktop" else ["mobile-state", 2]
    await page.evaluate("state => history.replaceState(state, '', location.href)", test_history_state)
    await page.evaluate("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            const rect = link.getBoundingClientRect();
            const top = rect.top + window.scrollY - window.innerHeight * 0.6;
            window.scrollTo({top, behavior: 'instant'});
        }
    """)
    await page.wait_for_function("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            const rect = link.getBoundingClientRect();
            return rect.top >= 0 && rect.bottom <= window.innerHeight;
        }
    """)
    await page.evaluate("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            link.href = 'https://dynacat-scroll-test.invalid/landing';
        }
    """)
    await page.evaluate("""
        () => window.addEventListener('click', function cancelFirstYouTubeClick(event) {
            const link = event.target.closest?.('a[href]');
            if (link?.textContent.trim() === 'YouTube') {
                event.preventDefault();
                window.removeEventListener('click', cancelFirstYouTubeClick);
            }
        });
    """)
    await page.get_by_role("link", name="YouTube", exact=True).click(timeout=10000)
    await page.wait_for_timeout(50)
    assert page.url == f"{BASE}/endpoints-services", {"device": label, "cancelled_click_navigated": page.url}
    pending = await page.evaluate("sessionStorage.getItem('__dynacatScrollY:/endpoints-services')")
    assert pending is None, {"device": label, "cancelled_click_left_stale_position": pending}

    await page.evaluate("() => window.scrollTo({top: Math.max(0, window.scrollY - 100), behavior: 'instant'})")
    await page.wait_for_function("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            const rect = link.getBoundingClientRect();
            return rect.top >= 0 && rect.bottom <= window.innerHeight;
        }
    """)
    before_click = await page.evaluate("({y: window.scrollY, height: document.documentElement.scrollHeight})")
    await page.get_by_role("link", name="YouTube", exact=True).click(timeout=10000)
    await page.wait_for_url("**dynacat-scroll-test.invalid/**")
    await page.go_back(wait_until="domcontentloaded")
    await page.wait_for_url(f"{BASE}/endpoints-services")
    await page.wait_for_selector(".es-endpoint")
    await page.wait_for_timeout(250)

    result = await page.evaluate("""
        () => ({
            restored: window.scrollY,
            clicked: Number(sessionStorage.getItem('__dynacat_scroll_test_clicked_y')),
            history_state: history.state,
            saved_position_remaining: sessionStorage.getItem('__dynacatScrollY:/endpoints-services'),
            restoration: history.scrollRestoration,
            max: document.documentElement.scrollHeight - innerHeight
        })
    """)
    await browser.close()
    assert result["clicked"] > 0, {"device": label, "before": before_click, "result": result}
    assert abs(result["restored"] - result["clicked"]) <= 1, {"device": label, "before": before_click, "result": result}
    assert result["history_state"] == test_history_state, {"device": label, "expected_state": test_history_state, "result": result}
    assert result["saved_position_remaining"] is None, {"device": label, "result": result}
    return {"device": label, "clicked_scroll": result["clicked"], "restored_scroll": result["restored"], "history_state": result["history_state"]}


async def verify_other_page_restoration(playwright, staged=False):
    browser = await playwright.chromium.launch()
    page = await browser.new_page(viewport={"width": 1365, "height": 768})
    if staged:
        source = load_same_tab_links_asset(staged)

        async def serve_staged_asset(route):
            await route.fulfill(status=200, content_type="application/javascript", body=source)

        await page.route("**/assets/same-tab-links.js*", serve_staged_asset)
    await page.goto(f"{BASE}/hardware-workloads", wait_until="load")
    restoration = await page.evaluate("history.scrollRestoration")
    await browser.close()
    assert restoration == "auto", {"route": "hardware-workloads", "restoration": restoration}
    return {"route": "hardware-workloads", "restoration": restoration}


async def verify_internal_back_restoration(playwright, staged=False):
    browser = await playwright.chromium.launch()
    page = await browser.new_page(viewport={"width": 1365, "height": 768})
    if staged:
        source = load_same_tab_links_asset(staged)

        async def serve_staged_asset(route):
            await route.fulfill(status=200, content_type="application/javascript", body=source)

        await page.route("**/assets/same-tab-links.js*", serve_staged_asset)
    await page.goto(f"{BASE}/endpoints-services", wait_until="load")
    await page.wait_for_selector(".es-endpoint")
    await page.evaluate("""
        () => window.scrollTo({
            top: Math.min(480, document.documentElement.scrollHeight - innerHeight),
            behavior: 'instant',
        })
    """)
    before = await page.evaluate("window.scrollY")
    restoration_before_navigation = await page.evaluate("history.scrollRestoration")
    await page.evaluate("""
        () => {
            const link = document.createElement('a');
            link.id = 'dynacat-internal-scroll-test';
            link.href = new URL('/hardware-workloads', location.href).href;
            link.textContent = 'Internal scroll QA destination';
            link.style.cssText = 'position:fixed;top:8px;left:8px;z-index:999999;background:white;color:black;padding:12px';
            document.body.append(link);
            window.addEventListener('click', event => {
                if (event.target.closest?.('#dynacat-internal-scroll-test')) {
                    sessionStorage.setItem('__dynacat_internal_scroll_clicked_y', String(window.scrollY));
                }
            });
        }
    """)
    await page.locator("#dynacat-internal-scroll-test").click()
    await page.wait_for_url(f"{BASE}/hardware-workloads")
    await page.go_back(wait_until="domcontentloaded")
    await page.wait_for_url(f"{BASE}/endpoints-services")
    await page.wait_for_selector(".es-endpoint")
    await page.wait_for_timeout(200)
    result = await page.evaluate("""
        () => ({
            clicked: Number(sessionStorage.getItem('__dynacat_internal_scroll_clicked_y')),
            restored: window.scrollY,
            restoration: history.scrollRestoration,
            saved_position: sessionStorage.getItem('__dynacatScrollY:/endpoints-services'),
        })
    """)
    await browser.close()
    assert before > 0, {"internal_back_scroll": before}
    assert result["clicked"] > 0, {"before": before, "result": result}
    assert restoration_before_navigation == "auto", {"internal_back_restoration_before_navigation": restoration_before_navigation}
    assert result["restored"] > 0, {"before": before, "result": result}
    assert abs(result["restored"] - result["clicked"]) <= 100, {"before": before, "result": result}
    assert result["restoration"] == "auto", {"before": before, "result": result}
    assert result["saved_position"] is None, {"before": before, "result": result}
    return {"internal_back_scroll": result["clicked"], "restored_scroll": result["restored"], "restoration": result["restoration"]}


async def verify_storage_failure_fallback(playwright, staged=False):
    browser = await playwright.chromium.launch()
    page = await browser.new_page(viewport={"width": 1365, "height": 768})
    if staged:
        source = load_same_tab_links_asset(staged)

        async def serve_staged_asset(route):
            await route.fulfill(status=200, content_type="application/javascript", body=source)

        await page.route("**/assets/same-tab-links.js*", serve_staged_asset)

    async def serve_external_destination(route):
        await route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>Scroll QA destination</title>")

    await page.route("https://dynacat-scroll-test.invalid/**", serve_external_destination)
    await page.add_init_script("""
        const nativeSetItem = Storage.prototype.setItem;
        Storage.prototype.setItem = function(key, value) {
            if (key.startsWith('__dynacatScrollY:') && !key.endsWith(':probe')) {
                throw new DOMException('simulated storage quota failure', 'QuotaExceededError');
            }
            return nativeSetItem.call(this, key, value);
        };
    """)
    await page.goto(f"{BASE}/endpoints-services", wait_until="load")
    await page.wait_for_function("Array.from(document.querySelectorAll('a')).some(a => a.textContent.trim() === 'YouTube')")
    await page.evaluate("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            const rect = link.getBoundingClientRect();
            window.scrollTo({top: rect.top + window.scrollY - innerHeight * 0.6, behavior: 'instant'});
        }
    """)
    await page.wait_for_function("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            const rect = link.getBoundingClientRect();
            return rect.top >= 0 && rect.bottom <= innerHeight;
        }
    """)
    await page.evaluate("""
        () => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'YouTube');
            link.href = 'https://dynacat-scroll-test.invalid/landing';
        }
    """)
    await page.evaluate("""
        () => window.addEventListener('click', event => {
            const link = event.target.closest?.('a[href]');
            if (link?.textContent.trim() === 'YouTube') {
                sessionStorage.setItem('__dynacat_scroll_test_restoration_at_click', history.scrollRestoration);
                sessionStorage.setItem('__dynacat_scroll_test_failed_write_y', String(window.scrollY));
            }
        });
    """)
    await page.get_by_role("link", name="YouTube", exact=True).click(timeout=10000)
    await page.wait_for_url("**dynacat-scroll-test.invalid/**")
    await page.go_back(wait_until="domcontentloaded")
    await page.wait_for_url(f"{BASE}/endpoints-services")
    restoration, clicked_y = await page.evaluate("""() => [
        sessionStorage.getItem('__dynacat_scroll_test_restoration_at_click'),
        Number(sessionStorage.getItem('__dynacat_scroll_test_failed_write_y')),
    ]""")
    restored_y = await page.evaluate("window.scrollY")
    await browser.close()
    assert restoration == "auto", {"storage_failure_restoration": restoration}
    assert clicked_y > 0, {"storage_failure_clicked_y": clicked_y}
    assert restored_y > 0, {"storage_failure_restored_y": restored_y}
    assert abs(restored_y - clicked_y) <= 100, {"clicked_y": clicked_y, "restored_y": restored_y}
    return {"storage_write_failure_restoration": restoration, "clicked_scroll": clicked_y, "restored_scroll": restored_y}


async def verify_storage_unavailable_at_startup(playwright, staged=False):
    browser = await playwright.chromium.launch()
    page = await browser.new_page(viewport={"width": 1365, "height": 768})
    if staged:
        source = load_same_tab_links_asset(staged)

        async def serve_staged_asset(route):
            await route.fulfill(status=200, content_type="application/javascript", body=source)

        await page.route("**/assets/same-tab-links.js*", serve_staged_asset)
    await page.add_init_script("""
        const nativeSetItem = Storage.prototype.setItem;
        Storage.prototype.setItem = function(key, value) {
            if (key.startsWith('__dynacatScrollY:')) {
                throw new DOMException('simulated unavailable storage', 'SecurityError');
            }
            return nativeSetItem.call(this, key, value);
        };
    """)
    await page.goto(f"{BASE}/endpoints-services", wait_until="load")
    restoration = await page.evaluate("history.scrollRestoration")
    await browser.close()
    assert restoration == "auto", {"storage_unavailable_restoration": restoration}
    return {"storage_unavailable_at_startup": restoration}


async def main(staged=False):
    async with async_playwright() as playwright:
        results = [
            await verify_device(playwright, "desktop", {"width": 1365, "height": 768}, staged=staged),
            await verify_device(playwright, "mobile", {"width": 390, "height": 844}, mobile=True, staged=staged),
        ]
        other_page = await verify_other_page_restoration(playwright, staged=staged)
        internal_back = await verify_internal_back_restoration(playwright, staged=staged)
        storage_failure = await verify_storage_failure_fallback(playwright, staged=staged)
        storage_unavailable = await verify_storage_unavailable_at_startup(playwright, staged=staged)
    print(json.dumps({"scroll_restoration": "passed", "staged_asset": staged, "results": results, "other_page": other_page, "internal_back": internal_back, "storage_failure": storage_failure, "storage_unavailable": storage_unavailable}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="serve the local same-tab-links.js asset")
    args = parser.parse_args()
    asyncio.run(main(staged=args.staged))
