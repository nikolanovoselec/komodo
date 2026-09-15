"""History storage is durable, non-root writable and needs no exited init job."""
from pathlib import Path
import unittest,yaml
ROOT=Path(__file__).parent
class HistoryDeployment(unittest.TestCase):
    def test_persistent_history_and_unchanged_service_lifecycles(self):
        doc=yaml.safe_load((ROOT/'compose.yaml').read_text());services=doc['services'];collector=services['workload-summary']
        self.assertEqual(set(services),{'workload-summary','dynacat','radio','geoip-update','gateway'})
        self.assertIn('telemetry-history:/history',collector['volumes'])
        self.assertIn('telemetry-history',doc['volumes'])
        self.assertEqual(collector['environment']['WORKLOAD_HISTORY_PATH'],'/history/workloads.sqlite')
        self.assertEqual(collector['environment']['MEDIA_HISTORY_PATH'],'/history/media.sqlite')
        self.assertEqual(collector['environment']['DYNACAT_UNIFI_TOKEN'],'${DYNACAT_UNIFI_TOKEN}')
        self.assertEqual(collector['user'],'65534:65534');self.assertTrue(collector['read_only'])
        dockerfile=(ROOT/'adapter/Dockerfile.geoip').read_text()
        self.assertIn('chown 65534:65534 /geoip /history',dockerfile)
        self.assertIn('/assets/telemetry-history.css?v=',(ROOT/'config/dynacat.yml').read_text())
if __name__=='__main__':unittest.main()
