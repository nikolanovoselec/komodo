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
        for name in ['NGINX Proxy Manager', 'Pihole Master', 'Pihole Slave', 'Pihole Storage']:
            a = next(a for a in soup.select('.es-endpoint') if a.select_one('strong').get_text(strip=True) == name)
            self.assertEqual(a['data-es-area'], 'infrastructure', name)
            self.assertEqual(a['data-es-group'], 'network-access', name)

    def test_all_original_urls_preserved_once(self):
        original = json.loads(BASELINE.read_text())
        actual = [(a.select_one('strong').get_text(strip=True), a['href']) for a in page_soup().select('.es-endpoint')]
        self.assertEqual(Counter(actual), Counter((r['name'],r['url']) for r in original))

    def test_global_applications_and_bookmark_groups_are_alphabetical(self):
        soup = page_soup()
        app_names = [a.select_one('strong').get_text(strip=True) for a in soup.select('.es-applications .es-endpoint')]
        self.assertEqual(app_names, sorted(app_names, key=str.casefold))
        groups = soup.select('.es-bookmarks .es-group')
        ids = [group['data-es-group'] for group in groups]
        self.assertEqual(len(ids), len(set(ids)))
        for group in groups:
            names = [a.select_one('strong').get_text(strip=True) for a in group.select('.es-endpoint')]
            self.assertEqual(names, sorted(names, key=str.casefold))

    def test_other_misclassifications_are_corrected(self):
        soup = page_soup()
        groups = {a.select_one('strong').get_text(strip=True):a.get('data-es-group') for a in soup.select('.es-endpoint')}
        expected = {'Gray Matter':'publishing','Codeflare':'ai-development','Codeflare Integration':'ai-development',
            'IT Tools':'ai-development','Hermes':'ai-development','Hermes Browser':'ai-development','Hermes Android':'ai-development',
            'Proxmox Backup Server':'backups','Backrest Media Servers':'backups','Torrentleech':'productivity-multimedia',
            'YouTube':'productivity-multimedia','Castopod':'publishing','Plex':'players','Tautulli':'media-management','Minecraft':'compute'}
        for name,group in expected.items():self.assertEqual(groups[name],group,name)

    def test_applications_and_bookmarks_remain_distinct_without_filter_chrome(self):
        soup = page_soup()
        self.assertEqual([d['data-es-domain'] for d in soup.select('.es-domain')], ['applications','personal'])
        self.assertIsNone(soup.select_one('.es-categories'))
        self.assertIsNone(soup.select_one('.es-toolbar'))
        groups = soup.select('.es-group')
        self.assertEqual(len(groups),4)
        titles=[g.select_one('h3').get_text(' ',strip=True) for g in groups]
        self.assertEqual(titles, ['News', 'Productivity & Multimedia', 'Shopping', 'Utilities'])
        self.assertEqual(
            {group['data-es-group']: len(group.select('.es-endpoint')) for group in groups},
            {'news': 7, 'productivity-multimedia': 8, 'shopping': 4, 'utilities': 6},
        )
        self.assertFalse(any(t.startswith(('Workspace ', 'Utilities ', 'Control plane ')) for t in titles))

    def test_third_party_hosted_services_are_bookmarks(self):
        expected = {
            'Cloudflare': 'utilities', 'Fast': 'utilities', 'Unifi': 'utilities',
            'YouTube': 'productivity-multimedia', 'Torrentleech': 'productivity-multimedia',
            'GitHub': 'utilities', 'NotebookLM': 'productivity-multimedia',
            'Renovate': 'utilities', 'Draw.io': 'productivity-multimedia',
            'Microsoft 365': 'productivity-multimedia', 'Outlook': 'productivity-multimedia',
            'Whiteboard': 'productivity-multimedia', 'LinkedIn': 'productivity-multimedia',
            'Resend': 'utilities',
        }
        directory = json.loads((ROOT / 'endpoints-directory.json').read_text())
        entries = {
            item['name']: (domain['id'], group['id'])
            for domain in directory['domains']
            for group in domain['groups']
            for item in group['links']
        }
        self.assertTrue(set(expected).issubset(entries))
        for name, group in expected.items():
            self.assertEqual(entries[name], ('personal', group), name)
        app_count = sum(len(group['links']) for domain in directory['domains'] if domain['id'] != 'personal' for group in domain['groups'])
        bookmark_count = sum(len(group['links']) for domain in directory['domains'] if domain['id'] == 'personal' for group in domain['groups'])
        self.assertEqual((app_count, bookmark_count), (52, 25))

    def test_flame_mdi_sprite_covers_every_endpoint(self):
        directory = json.loads((ROOT / 'endpoints-directory.json').read_text())
        icon_doc = json.loads((ROOT / 'flame-mdi-icons.json').read_text())
        items = [item for domain in directory['domains'] for group in domain['groups'] for item in group['links']]
        self.assertEqual(len(items), 77)
        self.assertTrue(all(item.get('icon') in icon_doc['icons'] for item in items))
        soup = page_soup()
        symbols = {symbol.get('id') for symbol in soup.select('.es-icon-sprite symbol')}
        self.assertEqual(symbols, {f'es-mdi-{name}' for name in icon_doc['icons']})
        for link in soup.select('.es-endpoint'):
            name = link.select_one('strong').get_text(strip=True)
            item = next(item for item in items if item['name'] == name)
            use = link.select_one('svg.es-icon use')
            self.assertIsNotNone(use, name)
            self.assertEqual(use.get('href'), f"#es-mdi-{item['icon']}", name)

    def test_launcher_uses_flat_flame_layout_without_search_chrome(self):
        soup = page_soup()
        self.assertIsNone(soup.select_one('.es-toolbar'))
        self.assertIsNone(soup.select_one('.es-search-row'))
        self.assertIsNone(soup.select_one('.es-categories'))
        self.assertEqual(soup.select_one('.es-applications h2').get_text(strip=True), 'Applications')
        self.assertEqual(soup.select_one('.es-bookmarks h2').get_text(strip=True), 'Bookmarks')

    def test_launcher_is_default_page(self):
        config = yaml.safe_load((ROOT / 'config/dynacat.yml').read_text())
        self.assertEqual(config['pages'][0].get('slug'), 'endpoints-services')

    def test_assets_match_content_hashes(self):
        import hashlib
        config=yaml.safe_load((ROOT/'config/dynacat.yml').read_text())
        for name in ['endpoint-directory.css','endpoints.js']:
            digest=hashlib.sha256((ROOT/'assets'/name).read_bytes()).hexdigest()[:12]
            self.assertIn(f'/assets/{name}?v={digest}',config['document']['head'])

if __name__ == '__main__':
    unittest.main()
