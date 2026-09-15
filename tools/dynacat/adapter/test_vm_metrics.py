import copy
import time
import unittest


class VMMetricsTests(unittest.TestCase):
    def fixture(self):
        guest = {'id': 131, 'name': 'tools', 'node': 'proxmox-iii', 'type': 'qemu',
                 'status': 'running', 'ram': {'used_bytes': 5, 'total_bytes': 4, 'percent': 125},
                 'disk': {'used_bytes': None, 'total_bytes': 50, 'percent': None},
                 'memory_scope': 'Host-accounted VM memory'}
        server = {'id': '6819f646d0f8c95b939cbf2f', 'name': 'renamed-komodo-host',
                  'info': {'state': 'Ok', 'address': 'https://192.168.2.72:8120',
                           'stats': {'mem_used_gb': 1.5, 'mem_total_gb': 4,
                                     'disk_used_gb': 10, 'disk_total_gb': 40,
                                     'refresh_ts': time.time() * 1000}}}
        return {'guest_inventory': [guest], 'nodes': [{'name': 'proxmox-iii'}],
                'guests': {'qemu': {'running': 1, 'total': 1}}}, [server]

    def test_verified_vm_gets_guest_bytes_preserving_host_ram_and_inventory(self):
        import vm_metrics
        pve, servers = self.fixture()
        before = copy.deepcopy(pve)
        result = vm_metrics.enrich(pve, servers)
        guest = result['guest_inventory'][0]
        self.assertEqual(guest['ram'], {'used_bytes': 1.5 * 1024**3,
                                      'total_bytes': 4 * 1024**3, 'percent': 37.5})
        self.assertEqual(guest['disk']['percent'], 25)
        self.assertEqual(guest['disk']['used_bytes'], 10 * 1024**3)
        self.assertEqual(guest['memory_source'], 'Komodo')
        self.assertEqual(guest['disk_source'], 'Komodo')
        self.assertEqual(guest['pve_host_ram'], before['guest_inventory'][0]['ram'])
        self.assertEqual(result['nodes'], before['nodes'])
        self.assertEqual(result['guests'], before['guests'])
        self.assertEqual(pve, before)
        for key in ('id', 'name', 'node', 'type', 'status'):
            self.assertEqual(guest[key], before['guest_inventory'][0][key])

    def test_display_renames_preserve_verified_vm_metrics(self):
        import vm_metrics
        for vmid, name in ((100, 'hermes'), (126, 'renamed-komodo-core')):
            pve, servers = self.fixture()
            binding = vm_metrics.VERIFIED_BINDINGS[vmid]
            pve['guest_inventory'][0].update(id=vmid, name=name)
            servers[0].update(id=binding[1], name='renamed-in-komodo')
            servers[0]['info']['address'] = binding[2]
            guest = vm_metrics.enrich(pve, servers)['guest_inventory'][0]
            self.assertEqual(guest['disk']['percent'], 25)
            self.assertEqual(guest['memory_source'], 'Komodo')
            self.assertEqual(guest['name'], name)

    def test_reaudited_hermes_server_restores_guest_metrics(self):
        import vm_metrics
        pve, servers = self.fixture()
        pve['guest_inventory'][0].update(id=100, name='hermes')
        servers[0].update(id='6aa9aec93b8fb630ffb9f88c', name='hermes')
        servers[0]['info']['address']='https://192.168.3.203:8120'
        guest=vm_metrics.enrich(pve,servers)['guest_inventory'][0]
        self.assertEqual(guest['disk']['percent'],25)
        self.assertEqual(guest['memory_source'],'Komodo')
        servers[0]['id']='6a9adf2e489ba7b3562cb584'
        self.assertEqual(vm_metrics.enrich(pve,servers),pve)

    def test_fail_closed_identity_state_and_freshness(self):
        import vm_metrics
        mutations = [
            lambda g, s: g.update(type='lxc'),
            lambda g, s: g.update(status='stopped'),
            lambda g, s: g.update(id=100, name='openclaw'),
            lambda g, s: g.update(id=131.0),
            lambda g, s: g.update(id='131'),
            lambda g, s: s.update(id='other-id'),
            lambda g, s: s['info'].update(state='Disabled'),
            lambda g, s: s['info'].update(state='NotOk'),
            lambda g, s: s['info'].update(address='https://other:8120'),
            lambda g, s: s['info']['stats'].update(refresh_ts=0),
            lambda g, s: s['info']['stats'].update(refresh_ts=float('nan')),
            lambda g, s: s['info']['stats'].update(refresh_ts=time.time()*1000+60000),
        ]
        for mutate in mutations:
            pve, servers = self.fixture()
            mutate(pve['guest_inventory'][0], servers[0])
            self.assertEqual(vm_metrics.enrich(pve, servers), pve)
        self.assertEqual(vm_metrics.enrich({'error': 'unavailable'}, []), {'error': 'unavailable'})

    def test_invalid_numbers_do_not_replace_either_metric(self):
        import vm_metrics
        for value in (None, '1.5', True, -1, float('nan'), float('inf'), 100):
            pve, servers = self.fixture()
            servers[0]['info']['stats'].update(mem_used_gb=value, disk_used_gb=value)
            self.assertEqual(vm_metrics.enrich(pve, servers), pve)
        pve, servers = self.fixture()
        servers[0]['info']['stats'].update(mem_total_gb=0, disk_total_gb=0)
        self.assertEqual(vm_metrics.enrich(pve, servers), pve)

    def test_independent_metrics_and_zero_usage(self):
        import vm_metrics
        pve, servers = self.fixture()
        servers[0]['info']['stats'].update(mem_used_gb=None, disk_used_gb=0)
        guest = vm_metrics.enrich(pve, servers)['guest_inventory'][0]
        self.assertEqual(guest['ram'], pve['guest_inventory'][0]['ram'])
        self.assertEqual(guest['disk']['percent'], 0)
        self.assertNotIn('memory_source', guest)

    def test_existing_actual_guest_metrics_are_not_overwritten(self):
        import vm_metrics
        pve, servers = self.fixture()
        guest = pve['guest_inventory'][0]
        guest.update(memory_scope='Guest OS memory', memory_source='QEMU guest agent',
                     ram={'used_bytes': 1, 'total_bytes': 2, 'percent': 50},
                     disk={'used_bytes': 3, 'total_bytes': 4, 'percent': 75},
                     disk_source='QEMU guest agent')
        self.assertEqual(vm_metrics.enrich(pve, servers), pve)


if __name__ == '__main__':
    unittest.main()
