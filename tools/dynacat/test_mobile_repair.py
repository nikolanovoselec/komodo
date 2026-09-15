"""Cached clients must request revised custom assets after dashboard deployment."""
from pathlib import Path
import re,unittest
ROOT=Path(__file__).parent
class MobileDeliveryTests(unittest.TestCase):
    def test_document_custom_assets_have_revision(self):
        head=next(line for line in (ROOT/'config/dynacat.yml').read_text().splitlines() if line.startswith('  head:'))
        paths=re.findall(r'(?:href|src)="(/assets/[^"]+)"',head)
        self.assertGreater(len(paths),5)
        self.assertTrue(all('?v=' in p for p in paths),paths)
        import hashlib
        from urllib.parse import urlsplit,parse_qs
        for path in paths:
            url=urlsplit(path)
            expected=hashlib.sha256((ROOT/url.path.lstrip('/')).read_bytes()).hexdigest()[:12]
            self.assertEqual(parse_qs(url.query)['v'],[expected],f'Changed asset must invalidate browser cache: {url.path}')
if __name__=='__main__':unittest.main()
