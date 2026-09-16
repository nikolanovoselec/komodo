import hashlib,re,unittest
from pathlib import Path
ROOT=Path(__file__).parent
class RefreshWiring(unittest.TestCase):
 def test_import_and_parent_cache_keys_match_source(self):
  gateway=(ROOT/'gateway.conf').read_text();digest=hashlib.sha256((ROOT/'assets/refresh-state.js').read_bytes()).hexdigest()[:12]
  self.assertIn(f'refresh-state.js?v={digest}',gateway)
  self.assertIn(f'&refresh-state={digest}',gateway)
 def test_poll_and_sse_prepare_before_native_dom_mutation(self):
  gateway=(ROOT/'gateway.conf').read_text()
  self.assertIn('preserveWidgetState(widgetElement, newWidget); if',gateway)
  self.assertIn('Idiomorph.morph(oldContent, newContent',gateway)
  self.assertIn('Idiomorph.morph(target, preserveDisclosureHTML(target, html)',gateway)
 def test_state_helper_has_no_scroll_override(self):
  source=(ROOT/'assets/refresh-state.js').read_text()
  for forbidden in ['setInterval','scrollTo(', 'scrollBy(', '.focus(']:self.assertNotIn(forbidden,source)
if __name__=='__main__':unittest.main()
