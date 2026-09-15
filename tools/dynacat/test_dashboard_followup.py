"""Regression contracts for the requested media ordering, size and navigation icons."""
from pathlib import Path
import unittest
ROOT=Path(__file__).parent
class FollowupTests(unittest.TestCase):
    def test_bandwidth_precedes_now_playing(self):
        text=(ROOT/'config/dynacat.yml').read_text()
        self.assertLess(text.index('<section class="mo-traffic"'),text.index('<div class="mo-section"><h3>Now playing'))
    def test_header_uses_uppercase_text_without_icons(self):
        text=(ROOT/'config/dynacat.yml').read_text()
        for label in ['HARDWARE & WORKLOADS','MEDIA','ENDPOINTS & SERVICES']:
            self.assertIn('name: '+label,text)
        self.assertIn('logo-text: THE CONSTRUCT',text)
        self.assertNotIn('name-icon:',text)
if __name__=='__main__':unittest.main()
