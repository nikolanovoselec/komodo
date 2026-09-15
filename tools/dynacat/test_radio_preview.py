"""Server-rendered Plex Radio contract; actual renderer exercised by qa_radio_preview.py."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).parent

def widget():
    config = yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
    page = next(p for p in config['pages'] if p['slug'] == 'media')
    return next((w for c in page['columns'] for w in c['widgets'] if w.get('css-class') == 'plex-radio-widget'), None)

class PreviewTemplateTests(unittest.TestCase):
    def test_native_preview_contains_initial_metadata_and_artwork(self):
        w = widget()
        self.assertIsNotNone(w, 'Missing native server-rendered Plex Radio preview widget')
        assert w is not None
        self.assertEqual(w['type'], 'custom-api')
        self.assertEqual(w['url'], 'http://radio:8091/radio/preview')
        self.assertEqual(w['cache'], '30s')
        template = w['template']
        for field in ['track.id', 'track.title', 'track.artist', 'track.album', 'track.codec', 'poster_base64']:
            self.assertIn('"'+field+'"', template)
        for marker in ['pr-server-preview', 'pr-title', 'pr-artist', 'pr-album', '<img', 'data-preview-id', 'Audio stays off', 'Press Play', '"error"']:
            self.assertIn(marker, template)
        self.assertNotIn('<audio', template)
        self.assertNotIn('autoplay', template)
        self.assertIn('src="data:image/jpeg;base64,{{ .JSON.String "poster_base64" }}"', template)

if __name__ == '__main__':
    unittest.main()
