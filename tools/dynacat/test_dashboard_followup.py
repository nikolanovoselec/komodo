"""Regression contracts for the requested media ordering, size and navigation icons."""
from pathlib import Path
import unittest
ROOT=Path(__file__).parent
class FollowupTests(unittest.TestCase):
    def test_bandwidth_precedes_now_playing(self):
        text=(ROOT/'config/dynacat.yml').read_text()
        self.assertLess(text.index('<section class="mo-traffic"'),text.index('<div class="mo-section"><h3>Now playing'))
    def test_header_icons_match_infrastructure_and_endpoints(self):
        text=(ROOT/'config/dynacat.yml').read_text()
        self.assertIn('name-icon: mdi:server-network',text)
        self.assertIn('name-icon: mdi:lan-connect',text)
if __name__=='__main__':unittest.main()
