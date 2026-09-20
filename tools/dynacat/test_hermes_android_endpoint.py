"""Regression coverage for the Hermes Android endpoint bookmark."""
import unittest
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
EXPECTED_NAME = "Hermes Android"
EXPECTED_URL = "https://hermes.novoselec.ch/android-app/"


class EndpointParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "es-endpoint" in (attrs.get("class") or ""):
            self.current = {"url": attrs["href"], "target": attrs.get("target"), "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            text = [part.strip() for part in self.current["text"] if part.strip() and part.strip() != "↗"]
            self.links.append((text[-2], self.current["url"], self.current["target"]))
            self.current = None


class HermesAndroidEndpoint(unittest.TestCase):
    def test_exact_name_and_url_are_present_once(self):
        config = yaml.safe_load((ROOT / "config/dynacat.yml").read_text())
        page = next(page for page in config["pages"] if page["name"] == "ENDPOINTS & SERVICES")
        widget = next(
            widget
            for column in page["columns"]
            for widget in column["widgets"]
            if widget["css-class"] == "endpoints-launcher"
        )
        parser = EndpointParser()
        parser.feed(widget["source"])
        matches = [link for link in parser.links if link[:2] == (EXPECTED_NAME, EXPECTED_URL)]
        self.assertEqual(matches, [(EXPECTED_NAME, EXPECTED_URL, None)])
        self.assertEqual(sum(name == EXPECTED_NAME for name, _, _ in parser.links), 1)
        self.assertEqual(sum(url == EXPECTED_URL for _, url, _ in parser.links), 1)


if __name__ == "__main__":
    unittest.main()
