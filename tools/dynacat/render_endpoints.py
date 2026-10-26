"""Render the centralized application launcher into Dynacat's native HTML widget."""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).parent


def render(directory):
    escape = lambda value: html.escape(str(value), quote=True)
    domains = directory["domains"]
    personal = next((domain for domain in domains if domain["id"] == "personal"), None)
    applications = [
        (domain, group, item)
        for domain in domains
        if domain["id"] != "personal"
        for group in domain["groups"]
        for item in group["links"]
    ]
    applications.sort(key=lambda record: record[2]["name"].casefold())
    bookmarks = [
        (group, item)
        for group in (personal or {}).get("groups", [])
        for item in group["links"]
    ]
    app_count = len(applications)
    bookmark_count = len(bookmarks)
    total = app_count + bookmark_count

    def endpoint(item, domain, group, area):
        name, url, description = item["name"], item["url"], item["description"]
        parsed = urlsplit(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Unsafe directory URL")
        search = " ".join([name, url, description, group["title"], domain["title"]])
        return (
            f'<li><a class="es-endpoint" data-es-area="{escape(area)}" data-es-group="{escape(group["id"])}" href="{escape(url)}" '
            f'rel="noopener noreferrer" data-es-search="{escape(search)}" title="{escape(url)}">'
            f'<span class="es-link-copy"><strong>{escape(name)}</strong><small>{escape(description)}</small></span>'
            '<span class="es-open" aria-hidden="true">↗</span></a></li>'
        )

    bits = [
        '<section class="es-launcher es-directory-v2" aria-label="Service directory">',
        '<header class="es-heading"><div><h2>Endpoints &amp; Services</h2><p>Find a service by what it does.</p></div>',
        f'<span class="es-inventory-label">{app_count} applications · {bookmark_count} bookmarks</span></header>',
        '<div class="es-toolbar"><div class="es-search-row"><label for="endpoint-search">Find a service</label>',
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>',
        '<input id="endpoint-search" type="search" placeholder="Search by name, purpose or address" autocomplete="off" spellcheck="false">',
        '<button type="button" class="es-clear" aria-label="Clear search" hidden>Clear</button></div>',
        '<nav class="es-categories" aria-label="Service areas">',
        '<button type="button" data-es-category="all" aria-pressed="true">All</button>',
    ]
    for domain in domains:
        count = sum(len(group["links"]) for group in domain["groups"])
        label = "Bookmarks" if domain["id"] == "personal" else domain["title"]
        bits.append(
            f'<button type="button" data-es-category="{escape(domain["id"])}" aria-pressed="false">'
            f'{escape(label)}<span>{count}</span></button>'
        )
    bits.extend(
        [
            "</nav></div>",
            f'<div class="es-results-line"><span class="es-result-count" aria-live="polite">{total} links</span>'
            "<span>Applications A–Z · bookmarks below</span></div>",
            '<section class="es-domain es-applications" data-es-domain="applications" aria-labelledby="es-applications-title">',
            '<header class="es-domain-header es-application-header"><h3 id="es-applications-title">Applications</h3>'
            f'<p>Core services · A–Z</p><span class="es-domain-count">{app_count}</span></header>',
            '<ul class="es-app-grid" aria-labelledby="es-applications-title">',
        ]
    )
    for domain, group, item in applications:
        bits.append(endpoint(item, domain, group, domain["id"]))
    bits.append("</ul></section>")

    if personal:
        bits.extend(
            [
                '<section class="es-domain es-bookmarks" data-es-domain="personal" aria-labelledby="es-domain-personal">',
                '<header class="es-domain-header"><h3 id="es-domain-personal">Bookmarks</h3>'
                f'<p>{escape(personal["description"])}</p><span class="es-domain-count">{bookmark_count}</span></header>',
                '<div class="es-group-grid">',
            ]
        )
        for group in personal["groups"]:
            links = sorted(group["links"], key=lambda item: item["name"].casefold())
            bits.extend(
                [
                    f'<section class="es-group" data-es-group="{escape(group["id"])}" '
                    'data-es-domain-key="personal" aria-labelledby="es-group-'
                    f'{escape(group["id"])}">',
                    f'<h4 id="es-group-{escape(group["id"])}">{escape(group["title"])}'
                    f'<span class="es-group-count">{len(links)}</span></h4><ul class="es-grid">',
                ]
            )
            for item in links:
                bits.append(endpoint(item, personal, group, "personal"))
            bits.append("</ul></section>")
        bits.append("</div></section>")

    bits.extend(
        [
            '<div class="es-empty" hidden><strong>No matching service</strong>'
            "<p>Try a name, purpose or hostname, or select All.</p></div>",
            "</section>",
        ]
    )
    return "".join(bits)


def main():
    path = ROOT / "config/dynacat.yml"
    original = path.read_text()
    config = yaml.safe_load(original)
    page = next(page for page in config["pages"] if page.get("slug") == "endpoints-services")
    result = render(json.loads((ROOT / "endpoints-directory.json").read_text()))

    # Preserve every unrelated YAML byte, including the other dashboard pages.
    start = original.index("- name: ENDPOINTS & SERVICES\n")
    end = original.index("\n- name:", start + 1)
    section = original[start:end]
    replacement, count = re.subn(
        r"^      source: .*$",
        lambda _: "      source: " + json.dumps(result, ensure_ascii=False),
        section,
        count=1,
        flags=re.M,
    )
    assert count == 1, "Launcher source changed; re-evaluate patch boundary"
    changed = original[:start] + replacement + original[end:]

    # Make the service directory the first page so root opens to the launcher.
    pages_start = changed.index("pages:\n") + len("pages:\n")
    launcher_start = changed.index("- name: ENDPOINTS & SERVICES\n", pages_start)
    launcher_end = changed.index("\n- name:", launcher_start + 1)
    launcher = changed[launcher_start:launcher_end]
    remaining = (changed[pages_start:launcher_start] + changed[launcher_end:]).lstrip("\n")
    changed = changed[:pages_start] + launcher + "\n" + remaining

    changed = changed.replace("/assets/endpoints.css?v=", "/assets/endpoint-directory.css?v=")
    for name in ("endpoint-directory.css", "endpoints.js"):
        digest = hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()[:12]
        changed = re.sub(
            r"(/assets/" + re.escape(name) + r"\?v=)[a-zA-Z0-9_-]+",
            lambda match: match[1] + digest,
            changed,
        )
    verified = yaml.safe_load(changed)
    new_page = next(page for page in verified["pages"] if page.get("slug") == "endpoints-services")
    assert new_page["columns"][0]["widgets"][0]["source"] == result
    path.write_text(changed)
    print("Application launcher rendered; all source endpoint records retained.")


if __name__ == "__main__":
    main()
