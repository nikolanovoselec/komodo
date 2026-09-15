"""Contract for the separately labelled Plex viewer row; rendered QA lives alongside it."""
from pathlib import Path
import unittest

ROOT = Path(__file__).parent

class SessionIdentityTest(unittest.TestCase):
    def test_user_is_labelled_before_content_with_independent_visual_treatment(self):
        template = next(line for line in (ROOT / 'config/dynacat.yml').read_text().splitlines() if '<div class="mo-players">' in line)
        self.assertIn('<span class="mo-session-user-label">USER</span>', template)
        self.assertLess(template.index('class="mo-session-viewer"'), template.index('<h3>'))
        css = (ROOT / 'assets/media-ops.css').read_text()
        viewer = css.split('.mo-players .mo-session-viewer{', 1)[1].split('}', 1)[0]
        self.assertIn('border-bottom:', viewer)
        self.assertIn('padding:', viewer)
        self.assertIn('font-weight:600', css.split('.mo-players .mo-session-viewer strong{', 1)[1].split('}', 1)[0])
        for preserved in ['popovertarget=', 'popover>', 'plex_url', 'mo-session-origin', 'mo-badge', 'mo-progress', 'bandwidth_kbps']:
            self.assertIn(preserved, template)

if __name__ == '__main__':
    unittest.main()
