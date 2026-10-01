import json
import unittest
from collections import Counter
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
BASELINE = ROOT / 'fixtures/endpoints-before-rebuild.json'

def page_soup():
    config = yaml.safe_load((ROOT / 'config/dynacat.yml').read_text())
    page = next(p for p in config['pages'] if p.get('slug') == 'endpoints-services')
    return BeautifulSoup(page['columns'][0]['widgets'][0]['source'], 'html.parser')

class DirectoryAcceptance(unittest.TestCase):
    def test_network_services_are_in_network_access_not_workspace(self):
        soup = page_soup()
        for name in ['NGINX Proxy Manager', 'Pihole Master', 'Pihole Slave', 'Pihole Storage', 'Unifi']:
            a = next(a for a in soup.select('.es-endpoint') if a.select_one('strong').get_text(strip=True) == name)
            self.assertEqual(a.find_parent('section')['data-es-group'], 'network-access', name)

    def test_all_original_urls_preserved_once(self):
        original = json.loads(BASELINE.read_text())
        actual = [(a.select_one('strong').get_text(strip=True), a['href']) for a in page_soup().select('.es-endpoint')]
        self.assertEqual(Counter(actual), Counter((r['name'],r['url']) for r in original))

    def test_each_group_is_alphabetical_and_unique(self):
        soup = page_soup()
        ids = [g['data-es-group'] for g in soup.select('.es-group')]
        self.assertEqual(len(ids), len(set(ids)))
        for group in soup.select('.es-group'):
            names = [a.select_one('strong').get_text(strip=True) for a in group.select('.es-endpoint')]
            self.assertEqual(names, sorted(names, key=str.casefold))

    def test_other_misclassifications_are_corrected(self):
        soup = page_soup()
        groups = {a.select_one('strong').get_text(strip=True):a.find_parent('section')['data-es-group'] for a in soup.select('.es-endpoint')}
        expected = {'Gray Matter':'publishing','Codeflare':'ai-development','Codeflare Integration':'ai-development',
            'IT Tools':'ai-development','Hermes':'ai-development','Hermes Browser':'ai-development','Hermes Android':'ai-development',
            'Proxmox Backup Server':'backups','Backrest Media Servers':'backups','Torrentleech':'downloads',
            'YouTube':'players','Castopod':'publishing','Plex':'players','Tautulli':'media-management','Minecraft':'compute'}
        for name,group in expected.items():self.assertEqual(groups[name],group,name)

    def test_four_clear_areas_and_no_catchall_groups(self):
        soup = page_soup()
        self.assertEqual([d['data-es-domain'] for d in soup.select('.es-domain')], ['infrastructure','media','work','personal'])
        self.assertEqual(len(soup.select('.es-group')),13)
        titles=[g.select_one('h4').get_text(' ',strip=True) for g in soup.select('.es-group')]
        self.assertFalse(any(t.startswith(('Workspace ', 'Utilities ', 'Control plane ')) for t in titles))

    def test_assets_match_content_hashes(self):
        import hashlib
        config=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        for name in ['endpoint-directory.css','endpoints.js']:
            digest=hashlib.sha256((ROOT/'assets'/name).read_bytes()).hexdigest()[:12]
            self.assertIn(f'/assets/{name}?v={digest}',config['document']['head'])

if __name__ == '__main__':
    unittest.main()
