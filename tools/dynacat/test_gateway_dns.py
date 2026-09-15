"""Upstreams must be re-resolved after Compose replaces a service."""
from pathlib import Path
import unittest
class GatewayDNS(unittest.TestCase):
    def test_runtime_service_resolution(self):
        config=Path(__file__).with_name('gateway.conf').read_text()
        self.assertIn('resolver 127.0.0.11 valid=5s ipv6=off;',config)
        for name,port in [('dynacat',8080),('radio',8091)]:
            self.assertIn(f'set ${name}_backend http://{name}:{port};',config)
            self.assertIn(f'proxy_pass ${name}_backend;',config)
            self.assertNotIn(f'proxy_pass http://{name}:{port};',config)
if __name__=='__main__':unittest.main()
