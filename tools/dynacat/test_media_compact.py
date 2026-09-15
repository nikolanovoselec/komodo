"""Guard the explicitly approved calmgraph block while compacting Plex sessions."""
import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).parent

class CompactScopeTests(unittest.TestCase):
    def test_approved_calmgraph_is_byte_exact(self):
        css=(ROOT/'assets/media-ops.css').read_text()
        block=css[css.index('/* Quiet host telemetry;'):css.index('.mo-players .mo-player{padding:0}')]
        self.assertEqual(hashlib.sha256(block.encode()).hexdigest(),
                         '7c88dff441dae986feb4918db005d1c777cbe25bf199625af054fe5a6558d040')

    def test_compact_css_cannot_target_radio_or_graph(self):
        css=(ROOT/'assets/media-ops.css').read_text()
        block=css[css.index('/* Compact existing Plex sessions;'):css.index('/* Quiet host telemetry;')]
        selectors=[line.split('{',1)[0] for line in block.splitlines() if '{' in line]
        self.assertTrue(selectors)
        self.assertTrue(all(s.startswith(('.mo-players ','.mo-session-')) for s in selectors))
        self.assertNotIn('.mo-traffic',block)
        self.assertNotIn('.pr-',block)

    def test_information_is_outside_plex_link(self):
        text=(ROOT/'config/dynacat.yml').read_text()
        line=next(x for x in text.splitlines() if '<div class="mo-players">' in x)
        self.assertLess(line.index('</a>'),line.index('<div class="mo-session-meta">'))
        for value in ['plex_url','poster','title','subtitle','state','mode','bandwidth_kbps',
                      'user','player','resolution','location','progress','imdb']:
            self.assertIn('"'+value+'"',line)
        self.assertIn('BW —',line)
        self.assertIn('aria-label="Session information for',line)
        self.assertIn('Plex reports no active playback.',line)

if __name__=='__main__':unittest.main()
