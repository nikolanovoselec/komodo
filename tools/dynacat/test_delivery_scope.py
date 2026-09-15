"""Delivery polish must not restyle qBittorrent, sessions or traffic."""
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).parent
class DeliveryScope(unittest.TestCase):
    def test_history_is_secondary_and_collapsed(self):
        d=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        for p in d['pages']:
            for c in p['columns']:
                for w in c['widgets']:
                    if w.get('title') in ('Sonarr delivery','Radarr delivery'):
                        t=w['template']
                        self.assertNotIn('class="mo-imports" open',t)
                        self.assertIn('class="mo-delivery-summary"',t)
                        self.assertIn('class="mo-import-meta"',t)
    def test_arr_only_scope(self):
        d=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        widgets={w.get('title'):w for p in d['pages'] for c in p['columns'] for w in c['widgets']}
        for title in ['Sonarr delivery','Radarr delivery']:
            self.assertIn('mo-arr-delivery',widgets[title]['template'])
        self.assertNotIn('mo-arr-delivery',widgets['qBittorrent']['template'])
        css=(ROOT/'assets/media-ops.css').read_text()
        block=css.split('/* Delivery-only stretched source links;',1)[1].split('.media-ops-widget>',1)[0]
        self.assertNotIn('.mo-delivery ',block)
if __name__=='__main__':unittest.main()
