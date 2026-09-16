"""Scoped Pi-hole template/asset contracts; no collector or Workloads mutations."""
import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'tools/dynacat/config/dynacat.yml'
CSS = ROOT / 'tools/dynacat/assets/networking.css'


def pihole(text):
    return text.split('<section class="nw-pihole">', 1)[1].split('</article>', 1)[0]


class PiholeFrontend(unittest.TestCase):
    def test_blacklist_is_direct_and_nonunique(self):
        panel = pihole(CONFIG.read_text())
        self.assertNotIn('<details', panel)
        self.assertIn('>Blacklist<', panel)
        self.assertIn('pihole.gravity_entries', panel)
        self.assertIn('entries across both instances', panel)
        self.assertIn('not deduplicated', panel)
        self.assertIn('Partial totals · available instances only.', panel)
        self.assertNotIn('pihole.instances', panel)

    def test_upstreams_direct_combined_with_honest_states(self):
        panel = pihole(CONFIG.read_text())
        self.assertIn('>Upstream DNS<', panel)
        self.assertIn('range .JSON.Array "pihole.configured_upstreams"', panel)
        self.assertIn('.JSON.Bool "pihole.upstreams_available"', panel)
        self.assertIn('.JSON.Bool "pihole.upstreams_truncated"', panel)
        self.assertIn('None configured', panel)
        self.assertIn('Configured forwarders', panel)
        self.assertIn('Upstream list incomplete', panel)

    def test_day_history_has_bounded_accessible_description(self):
        panel = pihole(CONFIG.read_text())
        self.assertEqual(panel.count('24h ·'), 2)
        self.assertEqual(panel.count('last 24 hours'), 2)
        self.assertEqual(panel.count('queries /10 min'), 2)
        self.assertEqual(panel.count('tabindex="0"'), 2)
        titles = re.findall(r'<title>(.*?)</title>', panel)
        self.assertEqual(len(titles), 2)
        for title in titles:
            self.assertLess(len(title), 300)
            self.assertNotIn('range', title)
            self.assertIn('UTC', title)
        self.assertNotIn('30-minute', panel)
        self.assertNotIn('30m', panel)
        self.assertNotIn('range .JSON.Array "pihole.query_history.bins"', panel)
        self.assertEqual(panel.count('query_history.start" }} UTC'), 2)
        self.assertEqual(panel.count('query_history.end" }} UTC'), 2)
        self.assertNotIn('No samples are extrapolated', panel)

    def test_direct_configuration_spans_full_card_and_warns_partial(self):
        rule = CSS.read_text().split('.nw-pihole .pm-dns-config{', 1)[1].split('}', 1)[0]
        self.assertIn('grid-column:1/-1', rule)
        self.assertIn('.JSON.Bool "pihole.upstreams_partial"', pihole(CONFIG.read_text()))
        self.assertIn('Configured forwarders incomplete', pihole(CONFIG.read_text()))

    def test_direct_config_and_dated_axes_have_scoped_responsive_styles(self):
        css = CSS.read_text()
        self.assertIn('.nw-pihole .pm-dns-config{', css)
        self.assertIn('.nw-pihole .pm-upstream-list{', css)
        self.assertIn('.nw-pihole .pm-upstream-list code{', css)
        self.assertIn('.nw-pihole .pve-netaxis{', css)
        self.assertIn('.nw-pihole .pve-netaxis>span:nth-child(2){grid-column:1/-1;grid-row:2}', css)
        self.assertIn('.nw-pihole .pve-netgraph:focus-visible{', css)
        digest = hashlib.sha256(CSS.read_bytes()).hexdigest()[:12]
        self.assertIn(f'/assets/networking.css?v={digest}', CONFIG.read_text())

    def test_non_pihole_markup_and_plot_geometry_unchanged(self):
        baseline = subprocess.check_output(['git', 'show', '2d56740a:tools/dynacat/config/dynacat.yml'], cwd=ROOT, text=True)
        current = re.sub(r"^  (favicon-url|app-icon-url|app-background-color):.*\n", "", CONFIG.read_text(), flags=re.M)
        strip = lambda text: re.sub(r'/assets/networking.css\?v=[a-f0-9]+', '/assets/networking.css', text.replace(pihole(text), 'PIHOLE'))
        self.assertEqual(strip(baseline), strip(current))
        self.assertIn('b42cecd68ff6', (ROOT / 'tools/dynacat/gateway.conf').read_text())
        self.assertEqual(hashlib.sha256((ROOT / 'tools/dynacat/assets/refresh-state.js').read_bytes()).hexdigest()[:12], 'b42cecd68ff6')
        geometry = lambda text: re.findall(r'<path class="(?:pm-area pm-requests|pm-area pm-blocks|pve-rx|pve-tx)"[^>]+>', pihole(text))
        self.assertEqual(geometry(baseline), geometry(current))
        baseline_css = subprocess.check_output(['git', 'show', '2d56740a:tools/dynacat/assets/networking.css'], cwd=ROOT, text=True)
        self.assertTrue(CSS.read_text().startswith(baseline_css))


if __name__ == '__main__':
    unittest.main()
