import unittest
import proxmox

class NavigationTests(unittest.TestCase):
    def test_native_summary_routes(self):
        self.assertTrue(hasattr(proxmox, 'resource_url'), 'Exact resource URL projection is missing')
        for kind, ident, suffix in [('node', 'proxmox-i', '4:5::::::'), ('qemu', 100, '4:::::5::'), ('lxc', 101, '4::::::5:')]:
            self.assertEqual(proxmox.resource_url(kind, ident), f'https://proxmox.graymatter.ch/#v1:0:={kind}%2F{ident}:{suffix}')
        for kind, ident in [('qemu', None), ('qemu', '../100'), ('node', 'evil/host'), ('bogus', 100), ('lxc', True)]:
            self.assertIsNone(proxmox.resource_url(kind, ident))

    def test_projection_preserves_guest_identity_and_links(self):
        guests = proxmox._guest_inventory([{'type': 'lxc', 'vmid': 101, 'name': 'mediaservers', 'node': 'proxmox-ii', 'status': 'stopped'}])
        self.assertEqual(guests[0].get('url'), 'https://proxmox.graymatter.ch/#v1:0:=lxc%2F101:4::::::5:')

    def test_disk_links_use_verified_pve_identity_not_komodo(self):
        import navigation
        summary = {'pve': {'guest_inventory': [{'type':'lxc', 'id':101, 'name':'mediaservers', 'url':proxmox.resource_url('lxc',101)}]}, 'top_disk':[{'server_id':'680f79cd6a6313ac1f9f2ab3','name':'media_servers','url':'wrong'}]}
        servers = [{'id':'680f79cd6a6313ac1f9f2ab3','info':{'address':'https://192.168.2.205:8120'}}]
        navigation.link_ranked_hosts(summary, servers)
        self.assertEqual(summary['top_disk'][0]['url'], proxmox.resource_url('lxc',101))
        servers[0]['info']['address'] = 'https://unverified:8120'
        navigation.link_ranked_hosts(summary, servers)
        self.assertIsNone(summary['top_disk'][0]['url'])

if __name__ == '__main__':
    unittest.main()
