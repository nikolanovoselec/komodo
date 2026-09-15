"""Deployment contract for offline-only Now Playing locations."""
from pathlib import Path
import unittest,yaml
ROOT=Path(__file__).parent
class GeoIntegration(unittest.TestCase):
    def test_collector_has_readonly_database_and_credential_free_updater(self):
        d=yaml.safe_load((ROOT/'compose.yaml').read_text());services=d['services']
        self.assertIn('geoip-city:/geoip:ro',services['workload-summary']['volumes'])
        updater=services['geoip-update']
        self.assertEqual(updater['restart'],'unless-stopped')
        self.assertIn('--watch',updater['command'])
        self.assertIn('--check',updater['healthcheck']['test'])
        self.assertNotIn('ports',updater)
        self.assertNotIn('environment',updater)
        self.assertNotIn('geoip-update',services['dynacat']['depends_on'])
    def test_location_is_visible_with_attribution_without_raw_address(self):
        text=(ROOT/'config/dynacat.yml').read_text()
        sessions=next(x for x in text.splitlines() if '<div class="mo-players">' in x)
        self.assertIn('.String "geo_label"',sessions)
        self.assertIn('IP Geolocation by DB-IP',text)
        self.assertNotIn('.String "address"',sessions)
if __name__=='__main__':unittest.main()
