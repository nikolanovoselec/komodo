"""Scoped ARR poster-template contract; native behavior is in qa_arr_thumbnail.py."""
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).parent
class ThumbnailContract(unittest.TestCase):
    def test_actual_poster_replaces_each_text_action(self):
        d=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        for w in [w for p in d['pages'] for c in p['columns'] for w in c['widgets'] if w.get('title') in ('Sonarr delivery','Radarr delivery')]:
            t=w['template']
            self.assertEqual(t.count('class="mo-imdb mo-arr-thumb"'),3)
            self.assertEqual(t.count('src="data:image/jpeg;base64,{{ .String "poster" }}"'),3)
            self.assertEqual(t.count('alt="Poster for {{ .String "title" }}"'),3)
            self.assertEqual(t.count('Poster unavailable'),3)
            self.assertNotIn('>IMDb ↗</a>',t)
if __name__=='__main__':unittest.main()
