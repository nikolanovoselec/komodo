"""Render the Flame-style application launcher into Dynacat's native HTML widget."""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).parent
ICON_PATHS = json.loads((ROOT / "flame-mdi-icons.json").read_text())["icons"]


def render(directory, icon_paths=None):
    escape = lambda value: html.escape(str(value), quote=True)
    icon_paths = ICON_PATHS if icon_paths is None else icon_paths
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
    used_icons = {item["icon"] for _, _, item in applications}
    used_icons.update(item["icon"] for _, item in bookmarks)
    missing_icons = used_icons - set(icon_paths)
    if missing_icons:
        raise ValueError(f"Missing MDI icon paths: {', '.join(sorted(missing_icons))}")

    def icon_sprite():
        symbols = []
        for name in sorted(used_icons):
            if not re.fullmatch(r"[a-z0-9-]+", name):
                raise ValueError(f"Invalid MDI icon name: {name}")
            paths = icon_paths[name]
            if isinstance(paths, str):
                paths = [paths]
            if not paths or not all(isinstance(path, str) and path for path in paths):
                raise ValueError(f"Invalid MDI icon path: {name}")
            path_markup = "".join(f'<path d="{escape(path)}"></path>' for path in paths)
            symbols.append(f'<symbol id="es-mdi-{escape(name)}" viewBox="0 0 24 24">{path_markup}</symbol>')
        return (
            '<svg class="es-icon-sprite" aria-hidden="true" focusable="false" '
            'xmlns="http://www.w3.org/2000/svg">'
            + "".join(symbols)
            + "</svg>"
        )

    def endpoint(item, domain, group, area):
        name, url, description, icon_name = item["name"], item["url"], item["description"], item["icon"]
        parsed = urlsplit(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Unsafe directory URL")
        icon_markup = (
            f'<svg class="es-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            f'<use href="#es-mdi-{escape(icon_name)}"></use></svg>'
        )
        description_markup = f"<small>{escape(description)}</small>" if area != "personal" else ""
        return (
            f'<li><a class="es-endpoint" data-es-area="{escape(area)}" '
            f'data-es-group="{escape(group["id"])}" data-es-icon="{escape(icon_name)}" '
            f'href="{escape(url)}" rel="noopener noreferrer" title="{escape(url)}">'
            f'{icon_markup}<span class="es-link-copy"><strong>{escape(name)}</strong>{description_markup}</span>'
            "</a></li>"
        )

    bits = [
        '<section class="es-directory-v2" aria-label="Service directory">',
        icon_sprite(),
        '<section class="es-domain es-applications" data-es-domain="applications" aria-labelledby="es-applications-title">',
        '<h2 class="es-section-title" id="es-applications-title">Applications</h2>',
        '<ul class="es-app-grid" aria-labelledby="es-applications-title">',
    ]
    for domain, group, item in applications:
        bits.append(endpoint(item, domain, group, domain["id"]))
    bits.extend(["</ul></section>"])

    if personal:
        bits.extend(
            [
                '<section class="es-domain es-bookmarks" data-es-domain="personal" aria-labelledby="es-bookmarks-title">',
                '<h2 class="es-section-title" id="es-bookmarks-title">Bookmarks</h2>',
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
                    f'<h3 id="es-group-{escape(group["id"])}">{escape(group["title"])}</h3><ul class="es-grid">',
                ]
            )
            for item in links:
                bits.append(endpoint(item, personal, group, "personal"))
            bits.append("</ul></section>")
        bits.append("</div></section>")
    bits.append("</section>")
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
    for name in ("endpoint-directory.css", "endpoints.js", "same-tab-links.js"):
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
    print("Flame-style launcher rendered; all source endpoint records retained.")


if __name__ == "__main__":
    main()
