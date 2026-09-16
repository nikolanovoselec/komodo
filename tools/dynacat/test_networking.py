"""NETWORKING contract tests; fixtures are synthetic, never live telemetry."""
from pathlib import Path
import unittest
import yaml
ROOT = Path(__file__).parent

class NetworkingTests(unittest.TestCase):
    def test_native_networking_page_between_hardware_and_media(self):
        config = yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        pages = config['pages']
        slugs = [p['slug'] for p in pages]
        self.assertIn('networking', slugs)
        self.assertEqual(slugs[:3], ['hardware-workloads', 'networking', 'media'])
        page = pages[1]
        widget = page['columns'][0]['widgets'][0]
        self.assertEqual(widget['url'], 'http://workload-summary:8090/network-current')
        self.assertEqual(widget['type'], 'custom-api')
        self.assertIn('nw-dashboard', widget['template'])

    def test_sparse_samples_remain_native_when_old_panels_are_removed(self):
        config = yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        t = next(p for p in config['pages'] if p.get('slug') == 'networking')['columns'][0]['widgets'][0]['template']
        self.assertNotIn('firewall.available', t)
        self.assertNotIn('firewall.rules', t)
        self.assertIn('history.cpu.dots', t)
        self.assertIn('<circle', t)

if __name__ == '__main__': unittest.main()
