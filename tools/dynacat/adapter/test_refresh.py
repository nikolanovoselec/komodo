import concurrent.futures
import json
from pathlib import Path
import re
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import adapter
import proxmox


class Refresh(unittest.TestCase):
    def test_stats_widgets_poll_and_refresh_render_cache_every_second(self):
        config = (Path(__file__).resolve().parents[1] / 'config/dynacat.yml').read_text()
        widgets = re.split(r'(?m)^    - type: ', config)
        stats = [widget for widget in widgets if re.search(
            r'^      css-class: .*\b(?:pve-resources|pve-guests|workload-attention|top-consumers)\b', widget, re.M)]
        self.assertEqual(len(stats), 4)
        for index, widget in enumerate(stats):
            with self.subTest(widget=index):
                self.assertRegex(widget, r'(?m)^      update-interval: 1s$')
                self.assertRegex(widget, r'(?m)^      cache: 1s$')
                route = 'pve-current' if 'pve-resources' in widget else 'current'
                self.assertIn('url: http://workload-summary:8090/' + route, widget)
                self.assertIn('.JSON.String "freshness.state"', widget)
                self.assertIn('.JSON.Float "freshness.age_seconds"', widget)
                self.assertIn('snapshot age', widget)
                self.assertIn('template: \'{{ if .JSON.String "error" }}<div class="k-warning">', widget)
                self.assertIn('{{ .JSON.String "error" }}</div>{{ else }}', widget)

    def test_cadence_labels_distinguish_ui_collection_and_source(self):
        config = (Path(__file__).resolve().parents[1] / 'config/dynacat.yml').read_text()
        self.assertIn('UI 1s · collector 5s · PVE ~10s · RRD 1m', config)
        self.assertIn('UI refresh 1s; collector cache 5s; PVE samples ~10s.', config)
        self.assertIn('UI refresh 1s · collector cache 5s', config)
        self.assertNotIn('5s refresh', config)
        self.assertNotIn('refresh 5s', config.lower())

    def test_summary_refreshes_at_five_seconds_single_flight(self):
        clock = [0.0]
        calls = []
        def load():
            calls.append(1)
            return {'generation': len(calls)}
        server = adapter.make_server(('127.0.0.1', 0), load)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def get(_=None):
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/summary') as response:
                return json.load(response)
        try:
            with patch('adapter.time.monotonic', side_effect=lambda: clock[0]):
                self.assertEqual(get(), {'generation': 1})
                # Four independently refreshed widgets read at 1 Hz, but the
                # shared collector must still run only once per five seconds.
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    for now in (1, 2, 3, 4, 4.9):
                        clock[0] = now
                        self.assertEqual(list(pool.map(get, range(4))), [{'generation': 1}] * 4)
                self.assertEqual(len(calls), 1)
                clock[0] = 5
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(get, range(8)))
                self.assertEqual(results, [{'generation': 2}] * 8)
                self.assertEqual(len(calls), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_failure_is_cached_without_serving_old_healthy_data(self):
        clock = [0.0]
        calls = []
        def load():
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError('secret')
            return {'ok': True}
        server = adapter.make_server(('127.0.0.1', 0), load)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/summary'
        try:
            with patch('adapter.time.monotonic', side_effect=lambda: clock[0]):
                urllib.request.urlopen(url).close()
                clock[0] = 5
                for _ in range(3):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(url)
                    self.assertEqual(error.exception.code, 503)
                    self.assertNotIn('secret', error.exception.read().decode())
                self.assertEqual(len(calls), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_projection_links_and_ranked_host_hook(self):
        server = {'id': 'host', 'name': 'Host', 'info': {'state': 'Ok',
                  'stats': {'disk_used_gb': 1, 'disk_total_gb': 2}}}
        self.assertEqual(adapter.project([server], [], [], [], set())['top_disk'][0].get('server_id'), 'host')
        guest = {'vmid': 100, 'type': 'qemu', 'status': 'running'}
        self.assertEqual(proxmox._guest_inventory([guest])[0].get('url'), proxmox.resource_url('qemu', 100))
        def read(path):
            return [{'node': 'pve', 'status': 'offline'}] if path == '/nodes' else []
        self.assertEqual(proxmox.collect(read)['nodes'][0].get('url'), proxmox.resource_url('node', 'pve'))
        with patch('proxmox.collect', return_value={'nodes': []}), patch('vm_metrics.enrich', return_value={'nodes': []}), patch('renovate.collect', return_value={}), patch('navigation.link_ranked_hosts') as link:
            result = adapter.collect(lambda kind, params: [server] if kind == 'ListServers' else [])
            link.assert_called_once_with(result, [server])

    def test_slow_failures_are_throttled_and_retry_at_expiry(self):
        clock = [0.0]
        calls = []
        def read(path, **kwargs):
            calls.append(path)
            raise RuntimeError('secret')
        cache = proxmox.SlowReadCache(read, clock=lambda: clock[0])
        for now in (0, 5, 59, 60):
            clock[0] = now
            with self.assertRaisesRegex(RuntimeError, '^Optional Proxmox telemetry unavailable$'):
                cache('/nodes/pve/disks/zfs')
        self.assertEqual(len(calls), 2)

    def test_slow_reads_cache_but_current_reads_do_not(self):
        clock = [0.0]
        calls = []
        def read(path, **kwargs):
            calls.append(path)
            return [{'value': len(calls)}]
        cache = proxmox.SlowReadCache(read, clock=lambda: clock[0])
        path = '/nodes/pve/rrddata?timeframe=hour&cf=AVERAGE'
        first = cache(path)
        first[0]['value'] = -1
        clock[0] = 5
        self.assertEqual(cache(path), [{'value': 1}])
        cache('/nodes')
        cache('/nodes')
        self.assertEqual(calls.count('/nodes'), 2)
        clock[0] = 60
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(cache, [path] * 8))
        self.assertEqual(calls.count(path), 2)


if __name__ == '__main__':
    unittest.main()
