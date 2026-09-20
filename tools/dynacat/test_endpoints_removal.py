"""Exact removal contract for the native Endpoints & Services bookmark widget."""
import unittest
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
REMOVED = {
    ("Backrest Synology", "https://backrest-nas.graymatter.ch", "Backup and restore"),
    ("Heimdall", "https://heimdall.graymatter.ch", "Dashboard"),
    ("Synology", "https://nas.graymatter.ch/?forceDesktop=stay_desktop#/signin", "Network attached storage"),
    ("Huntarr", "https://huntarr.graymatter.ch", "Missing media finder"),
    ("Lidarr", "https://lidarr.graymatter.ch", "Music manager and requester"),
    ("Spotifux", "https://spotifux.novoselec.ch", "Spotify Ass Jockey"),
    ("Nextcloud", "https://nextcloud.novoselec.ch/", "Self-Hosted Office Stack"),
    ("ChatGPT", "https://chatgpt.com", "chatgpt.com"),
    ("Claude", "https://claude.ai", "claude.ai"),
    ("Gemini", "https://gemini.google.com", "gemini.google.com"),
}
RETAINED = {
    ("Backrest Komodo", "https://backrest-komodo.graymatter.ch", "Backup and restore"),
    ("Plex", "https://plex.novoselec.ch", "Media server"),
    ("LinkedIn", "https://www.linkedin.com", "www.linkedin.com"),
    ("YouTube", "https://www.youtube.com", "www.youtube.com"),
}


class EndpointParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "es-endpoint" in (attrs.get("class") or ""):
            self.current = {"url": attrs["href"], "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            text = [part.strip() for part in self.current["text"] if part.strip() and part.strip() != "↗"]
            self.links.append((text[-2], self.current["url"], text[-1]))
            self.current = None


def endpoint_links(config):
    page = next(page for page in config["pages"] if page["name"] == "ENDPOINTS & SERVICES")
    widget = next(widget for column in page["columns"] for widget in column["widgets"] if widget["css-class"] == "endpoints-launcher")
    parser = EndpointParser()
    parser.feed(widget["source"])
    return set(parser.links)


class EndpointsRemoval(unittest.TestCase):
    def test_exact_requested_cards_are_absent_and_retained_cards_remain(self):
        config = yaml.safe_load((ROOT / "config/dynacat.yml").read_text())
        links = endpoint_links(config)
        self.assertTrue(REMOVED.isdisjoint(links), f"requested cards still visible: {sorted(REMOVED & links)}")
        self.assertTrue(RETAINED.issubset(links), f"retained cards missing: {sorted(RETAINED - links)}")
        self.assertEqual(len(links), 77)


if __name__ == "__main__":
    unittest.main()
