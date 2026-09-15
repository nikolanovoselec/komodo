import importlib
import json
import unittest
from unittest.mock import patch


class Proxmox(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('proxmox')
        except ModuleNotFoundError:
            self.fail('Proxmox collector module is missing')

    def test_physical_zfs_pool_capacity_is_not_root_disk_or_storage_capacity(self):
        pve = self.module()
        data = {'/nodes': [dict(node='pve-i', status='online', disk=1, maxdisk=2)],
                '/cluster/resources?type=vm': [],
                '/nodes/pve-i/disks/zfs': [dict(name='rpool', alloc=40, size=100, free=60)]}
        node = pve.collect(data.__getitem__)['nodes'][0]
        self.assertEqual(node['zfs'], [dict(name='rpool', used_bytes=40, total_bytes=100,
                                         free_bytes=60, percent=40, scope='physical_pool')])
        self.assertEqual(node['zfs_state'], 'ok')
        self.assertIsNone(node['zfs_error'])

    def test_zfs_storage_fallback_deduplicates_pool_aliases_and_datasets(self):
        pve = self.module()
        data = {'/nodes': [dict(node='pve-i', status='online')],
                '/cluster/resources?type=vm': [],
                '/storage': [dict(storage='root', type='zfspool', pool='rpool'),
                             dict(storage='alias', type='zfspool', pool='rpool'),
                             dict(storage='child', type='zfspool', pool='rpool/data'),
                             dict(storage='nas', type='cifs')],
                '/nodes/pve-i/storage': [dict(storage=s, type=t, active=1, enabled=1,
                                              used=25, total=100, avail=75)
                                         for s, t in [('root', 'zfspool'), ('alias', 'zfspool'),
                                                      ('child', 'zfspool'), ('nas', 'cifs')]]}
        node = pve.collect(data.__getitem__)['nodes'][0]
        self.assertEqual(node['zfs'], [dict(name='rpool', used_bytes=25, total_bytes=100,
                                          free_bytes=75, percent=25, scope='zfs_backed_storage')])
        self.assertEqual(node['zfs_state'], 'fallback')
        self.assertIn('not physical pool', node['zfs_error'])

    def test_zfs_allowlist_rejects_unrelated_reads_even_if_caller_lists_them(self):
        pve = self.module()
        with patch('urllib.request.build_opener') as transport:
            for path in ['/access/users', '/nodes/pve-i/disks/list',
                         '/nodes/../storage', '/nodes/pve-i/storage/local/content',
                         '/storage?content=images']:
                with self.assertRaises(ValueError):
                    pve._api(path, allowed_rrd=frozenset([path]))
        transport.assert_not_called()

    def test_zfs_malformed_pool_rows_are_unknown_not_no_pools(self):
        pve = self.module()
        for rows in [[None], [{}], [dict(name='rpool', alloc=-1, size=100, free=10)],
                     [dict(name='rpool', alloc=40, size=100, free=90)]]:
            with self.subTest(rows=rows):
                result = pve._zfs(dict(node='pve-i', status='online'), lambda path: rows)
                self.assertEqual(result['zfs_state'], 'unavailable')
                self.assertIsNotNone(result['zfs_error'])
                if result['zfs']:
                    self.assertIsNone(result['zfs'][0]['used_bytes'])
                json.dumps(result, allow_nan=False)

    def test_zfs_empty_offline_and_failed_endpoints_have_distinct_states(self):
        pve = self.module()
        online = dict(node='pve-i', status='online')
        self.assertEqual(pve._zfs(online, lambda path: [])['zfs_state'], 'none')
        def failing(path):
            raise RuntimeError('private-token')
        result = pve._zfs(online, failing)
        self.assertIsNone(result['zfs'])
        self.assertEqual(result['zfs_state'], 'unavailable')
        self.assertNotIn('private-token', json.dumps(result))
        calls = []
        result = pve._zfs(dict(node='pve-i', status='offline'), calls.append)
        self.assertEqual(result['zfs_state'], 'offline')
        self.assertEqual(calls, [])

    def test_collect_projects_nodes_and_guest_counts_only(self):
        pve = self.module()
        data = {'/nodes': [dict(node='pve1', status='online', cpu=.25, mem=50,
                               maxmem=100, disk=20, maxdisk=80, config='private')],
                '/cluster/resources?type=vm': [dict(type=t, node='pve1', status=s, vmid=i,
                                                    name='guest', secret='private')
                                               for i, (t, s) in enumerate([
                                                   ('qemu', 'running'), ('qemu', 'stopped'),
                                                   ('lxc', 'running')])]}
        result = pve.collect(data.__getitem__)
        self.assertIsNone(result['error'])
        self.assertEqual(result['guests'], {'qemu': {'running': 1, 'total': 2},
                                           'lxc': {'running': 1, 'total': 1}})
        node = result['nodes'][0]
        self.assertEqual(node['name'], 'pve1')
        self.assertEqual(node['cpu_percent'], 25)
        self.assertEqual(node['ram'], {'used_bytes': 50, 'total_bytes': 100, 'percent': 50})
        self.assertEqual(node['root_disk'], {'used_bytes': 20, 'total_bytes': 80, 'percent': 25})
        self.assertEqual(node['guests'], result['guests'])
        self.assertNotIn('private', json.dumps(result))

    def test_rrd_history_is_real_time_ordered_and_rates_are_not_counters(self):
        pve = self.module()
        calls = []
        def api(path):
            calls.append(path)
            if path == '/nodes':
                return [dict(node='pve-iii', status='online'),
                        dict(node='pve-i', status='online'), dict(node='pve-ii', status='online')]
            if path == '/cluster/resources?type=vm':
                return []
            if path.endswith('/disks/zfs'):
                return []
            self.assertIn(path, ['/nodes/pve-' + n + '/rrddata?timeframe=hour&cf=AVERAGE'
                                 for n in ('i', 'ii', 'iii')])
            return [dict(time=300, cpu=1, netin=125, netout=250),
                    dict(time=100, cpu=0), dict(time=200, cpu=.5)]
        result = pve.collect(api)
        self.assertIsNone(result['error'])
        self.assertEqual([n['name'] for n in result['nodes']], ['pve-i', 'pve-ii', 'pve-iii'])
        for node in result['nodes']:
            self.assertEqual(node['history'], {'cpu_points': '0,30 50,15 100,0',
                                               'samples': 3, 'window': '1h'})
            self.assertEqual(node['net_in_bytes_sec'], 125)
            self.assertEqual(node['net_out_bytes_sec'], 250)
        self.assertEqual(calls[0], '/nodes')

    def test_offline_or_invalid_metrics_are_unknown_not_zero(self):
        pve = self.module()
        nodes = [dict(node='offline', status='offline'),
                 dict(node='bad', status='online', cpu=float('nan'), mem=-1, maxmem=0,
                      disk=101, maxdisk=100)]
        result = pve.collect(lambda path: nodes if path == '/nodes' else [])
        for node in result['nodes']:
            self.assertIsNone(node['cpu_percent'])
            self.assertIsNone(node['ram']['percent'])
            self.assertIsNone(node['root_disk']['percent'])
        json.dumps(result, allow_nan=False)

    def test_optional_rrd_failure_and_offline_nodes_keep_current_telemetry(self):
        pve = self.module()
        calls = []
        def api(path):
            calls.append(path)
            if path == '/nodes':
                return [dict(node='pve-i', status='online', cpu=.2),
                        dict(node='pve-ii', status='offline'),
                        dict(node='bad/../path', status='online')]
            if path == '/cluster/resources?type=vm':
                return []
            raise RuntimeError('private RRD token')
        result = pve.collect(api)
        self.assertIsNone(result['error'])
        online = next(n for n in result['nodes'] if n['name'] == 'pve-i')
        self.assertEqual(online['cpu_percent'], 20)
        self.assertEqual(calls, ['/nodes', '/cluster/resources?type=vm',
                                '/nodes/pve-i/rrddata?timeframe=hour&cf=AVERAGE',
                                '/nodes/pve-i/disks/zfs', '/storage'])
        for node in result['nodes']:
            self.assertEqual(node['history'], {'cpu_points': None, 'samples': 0, 'window': '1h'})
            self.assertIsNone(node['net_in_bytes_sec'])
            self.assertIsNone(node['net_out_bytes_sec'])
        self.assertNotIn('private', json.dumps(result))

    def test_invalid_rrd_values_are_null_and_svg_coordinates_are_bounded(self):
        pve = self.module()
        result = pve._history([None, {}, dict(time=float('nan'), cpu=.5),
                               dict(time=0, cpu=-1), dict(time=1, cpu=2),
                               dict(time=2, cpu=True), dict(time=3, cpu=float('inf')),
                               dict(time=4, cpu=.4, netin=-1, netout=float('nan'))])
        self.assertEqual(result['history'], {'cpu_points': '0,18', 'samples': 1, 'window': '1h'})
        self.assertIsNone(result['net_in_bytes_sec'])
        self.assertIsNone(result['net_out_bytes_sec'])
        json.dumps(result, allow_nan=False)

    def test_undiscovered_rrd_and_mutating_paths_are_rejected_before_transport(self):
        pve = self.module()
        with patch('urllib.request.build_opener') as transport:
            for path in ['/nodes/pve-i/rrddata?timeframe=hour&cf=AVERAGE',
                         '/nodes/pve-i/status', '/nodes/../access/users', '/access/users']:
                with self.assertRaises(ValueError):
                    pve._api(path)
        transport.assert_not_called()

    def test_api_failure_is_separate_and_never_exposes_exception(self):
        pve = self.module()
        def failing(path):
            raise RuntimeError('private-token-and-url')
        result = pve.collect(failing)
        self.assertEqual(result['error'], 'Proxmox telemetry unavailable; verify TLS, network and read API access')
        self.assertIsNone(result['guests'])
        self.assertEqual(result['nodes'], [])
        self.assertNotIn('private', json.dumps(result))

    def test_default_transport_is_verified_https_read_only_and_bounded(self):
        import io
        import ssl
        pve = self.module()
        calls = []
        context = ssl.create_default_context()
        # Python 3.13 enables STRICT by default; simulate it on older test hosts.
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        original_flags = context.verify_flags
        def open_request(request, **kwargs):
            calls.append((request, kwargs))
            data = [dict(node='pve-i', status='online')] if request.full_url.endswith('/nodes') else []
            return io.BytesIO(json.dumps({'data': data}).encode())
        with patch.dict('os.environ', {'DYNACAT_PROXMOX_TOKEN_ID': 'reader@pve!dash',
                                      'DYNACAT_PROXMOX_SECRET': 'test-only-placeholder'}, clear=True), \
             patch('ssl.create_default_context', return_value=context) as tls, \
             patch('urllib.request.build_opener') as build:
            build.return_value.open.side_effect = open_request
            result = pve.collect()
        self.assertIsNone(result['error'])
        self.assertEqual(context.verify_flags, original_flags & ~ssl.VERIFY_X509_STRICT)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        tls.assert_called_with(cafile='/app/pve-root-ca.pem')
        self.assertEqual(len(calls), 4)
        self.assertTrue(calls[-1][0].full_url.endswith('/nodes/pve-i/disks/zfs'))
        handlers = build.call_args.args
        import urllib.request
        https = next(h for h in handlers if isinstance(h, urllib.request.HTTPSHandler))
        redirect = next(h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
        from http.client import HTTPMessage
        self.assertIs(getattr(https, '_context'), context)
        self.assertIsNone(redirect.redirect_request(urllib.request.Request('https://pve/'),
                         io.BytesIO(), 302, 'Found', HTTPMessage(), 'https://other/'))
        for request, kwargs in calls:
            self.assertTrue(request.full_url.startswith('https://192.168.1.2:8006/api2/json/'))
            self.assertEqual(request.get_method(), 'GET')
            self.assertEqual(request.get_header('Authorization'), 'PVEAPIToken=reader@pve!dash=test-only-placeholder')
            self.assertGreater(kwargs['timeout'], 0)
            self.assertLessEqual(kwargs['timeout'], 2)
        self.assertNotIn('test-only-placeholder', json.dumps(result))

    def test_insecure_url_is_rejected_before_sending_credentials(self):
        pve = self.module()
        with patch.dict('os.environ', {'PVE_URL': 'http://pve/api2/json'}, clear=True), \
             patch('ssl.create_default_context') as tls, \
             patch('urllib.request.build_opener') as transport:
            result = pve.collect()
        self.assertIsNotNone(result['error'])
        tls.assert_not_called()
        transport.assert_not_called()


if __name__ == '__main__':
    unittest.main()
