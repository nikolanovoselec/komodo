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
        def open_request(request, **kwargs):
            calls.append((request, kwargs))
            return io.BytesIO(b'{"data": []}')
        with patch.dict('os.environ', {'DYNACAT_PROXMOX_TOKEN_ID': 'reader@pve!dash',
                                      'DYNACAT_PROXMOX_SECRET': 'test-only-placeholder'}, clear=True), \
             patch('ssl.create_default_context', return_value=context) as tls, \
             patch('urllib.request.build_opener') as build:
            build.return_value.open.side_effect = open_request
            result = pve.collect()
        self.assertIsNone(result['error'])
        tls.assert_called_with(cafile='/app/pve-root-ca.pem')
        self.assertEqual(len(calls), 2)
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
