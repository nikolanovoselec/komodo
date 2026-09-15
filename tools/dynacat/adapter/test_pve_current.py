"""Independent physical telemetry HTTP regressions; no live upstream calls."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import adapter


class PveCurrent(unittest.TestCase):
    def setUp(self):
        cache = patch.object(adapter, '_pve_cache', adapter.PveSnapshot())
        cache.start()
        self.addCleanup(cache.stop)

    def test_general_collection_reuses_raw_pve_without_enrichment_mutation(self):
        raw = {'error': None, 'fetched_at': 123, 'nodes': [{'name': 'physical'}],
               'guest_inventory': []}
        with patch('proxmox.collect', return_value=raw) as upstream, \
             patch('renovate.collect', return_value={'prs': []}):
            adapter._pve_cache.snapshot(wait=True)
            result = adapter.collect(lambda kind, params: [])
            self.assertEqual(upstream.call_count, 1)
            result['pve']['nodes'][0]['name'] = 'mutated'
            self.assertEqual(adapter._pve_cache.snapshot()[0]['nodes'][0]['name'], 'physical')

    def test_freshness_discloses_collector_not_source_sample_time(self):
        cache = adapter.PveSnapshot(lambda: {'nodes': [], 'fetched_at': 123})
        _, freshness, status = cache.snapshot(wait=True)
        self.assertEqual(status, 200)
        self.assertEqual(freshness.get('age_basis'), 'collection_started')
        self.assertEqual(freshness.get('fetched_at_basis'), 'collection_completed_not_source_sample')

    def test_failure_preserves_error_shape_without_leaking_upstream_message(self):
        cache = adapter.PveSnapshot(lambda: {'error': 'private-token', 'nodes': [],
                                            'guests': None, 'fetched_at': 123})
        data, freshness, status = cache.snapshot(wait=True)
        self.assertEqual(status, 503)
        self.assertEqual(data.get('fetched_at'), 123)
        self.assertEqual(data['nodes'], [])
        self.assertNotIn('private-token', json.dumps(data))
        self.assertEqual(freshness['state'], 'unavailable')

    def test_blocked_refresh_serves_bounded_snapshot_then_expires_singleflight(self):
        now, calls = [0], []
        entered, release = threading.Event(), threading.Event()
        def load():
            calls.append(now[0])
            if len(calls) > 1:
                entered.set()
                release.wait(5)
            return {'nodes': [{'name': 'physical'}], 'fetched_at': 123}
        cache = adapter.PveSnapshot(load, clock=lambda: now[0])
        self.addCleanup(release.set)
        cache.snapshot(wait=True)
        now[0] = 5
        self.assertEqual(cache.snapshot()[1]['state'], 'collecting')
        self.assertTrue(entered.wait(1))
        for _ in range(20):
            data, freshness, status = cache.snapshot()
            self.assertEqual(status, 200)
            self.assertEqual(data['nodes'][0]['name'], 'physical')
        self.assertEqual(calls, [0, 5])
        now[0] = 30
        with patch.object(adapter, '_pve_cache', cache):
            server = self.start_server(lambda: {})
            status, _, body = self.get(server, '/pve-current')
        self.assertEqual(status, 503)
        self.assertEqual(body['pve']['nodes'], [])
        self.assertEqual(body['freshness']['state'], 'expired')
        self.assertEqual(body['freshness']['age_seconds'], 30)
        # A very late result must not regain a healthy state on completion.
        now[0] = 35
        release.set()
        self.assertEqual(cache.snapshot(wait=True)[1]['state'], 'expired')
        self.assertEqual(calls, [0, 5])

    def test_failure_invalidates_previous_success_and_throttles_retries(self):
        for failure in ('exception', 'error', 'serialization'):
            with self.subTest(failure=failure):
                now, calls = [0], []
                def load():
                    calls.append(now[0])
                    if len(calls) == 1:
                        return {'nodes': [{'name': 'physical'}]}
                    if failure == 'exception':
                        raise RuntimeError('private-token')
                    return {'error': 'private-token'} if failure == 'error' else {'nodes': {object()}}
                cache = adapter.PveSnapshot(load, clock=lambda: now[0])
                self.assertEqual(cache.snapshot(wait=True)[2], 200)
                now[0] = 5
                data, freshness, status = cache.snapshot(wait=True)
                self.assertEqual(status, 503)
                self.assertEqual(freshness['state'], 'unavailable')
                self.assertEqual(data['nodes'], [])
                self.assertNotIn('private-token', json.dumps(data))
                for second in (5, 6, 7, 8, 9):
                    now[0] = second
                    self.assertEqual(cache.snapshot()[2], 503)
                self.assertEqual(calls, [0, 5])
                now[0] = 10
                cache.snapshot(wait=True)
                self.assertEqual(calls, [0, 5, 10])

    def test_cold_start_returns_starting_while_singleflight_is_blocked(self):
        entered, release = threading.Event(), threading.Event()
        def load():
            entered.set()
            release.wait(5)
            return {'nodes': []}
        cache = adapter.PveSnapshot(load)
        self.addCleanup(release.set)
        with patch.object(adapter, '_pve_cache', cache):
            server = self.start_server(lambda: {})
            status, _, body = self.get(server, '/pve-current')
            self.assertTrue(entered.wait(1))
            self.assertEqual(status, 503)
            self.assertEqual(body['freshness']['state'], 'starting')
            self.assertIsNone(body['freshness']['age_seconds'])
            self.assertEqual(body['pve']['nodes'], [])
            release.set()
            cache.snapshot(wait=True)
            self.assertEqual(self.get(server, '/pve-current')[0], 200)

    def start_server(self, loader):
        server = adapter.make_server(('127.0.0.1', 0), loader)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def get(self, server, path):
        try:
            response = urllib.request.urlopen(
                f'http://127.0.0.1:{server.server_port}{path}', timeout=1)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.headers.get_content_type(), 'application/json')
            return response.status, dict(response.headers), json.load(response)

    def test_blocked_general_loader_cannot_block_pve_snapshot(self):
        entered, release = threading.Event(), threading.Event()
        def blocked():
            entered.set()
            release.wait(5)
            raise RuntimeError('private Komodo failure')
        self.addCleanup(release.set)
        now = [0]
        adapter._pve_cache = adapter.PveSnapshot(clock=lambda: now[0])
        with patch('proxmox.collect', return_value={'error': None, 'fetched_at': 123,
                                                   'nodes': [{'name': 'physical'}]}) as upstream:
            server = self.start_server(blocked)
            self.assertEqual(self.get(server, '/current')[0], 503)
            self.assertTrue(entered.wait(1))
            status, headers, body = self.get(server, '/pve-current')
            self.assertIn(status, (200, 503))  # Cold start is explicitly nonblocking.
            if status == 503:
                self.assertEqual(body['freshness']['state'], 'starting')
            # Join only the independent PVE attempt, never the blocked general one.
            adapter._pve_cache.snapshot(wait=True)
            status, headers, body = self.get(server, '/pve-current')
            self.assertEqual(status, 200)
            self.assertEqual(body['pve']['nodes'], [{'name': 'physical'}])
            self.assertEqual(body['pve']['fetched_at'], 123)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(body['freshness']['max_age_seconds'], 30)
            self.assertFalse(release.is_set())
            release.set()
            self.assertEqual(self.get(server, '/summary')[0], 503)
            now[0] = 5
            upstream.return_value = {'error': None, 'fetched_at': 128,
                                     'nodes': [{'name': 'physical', 'cpu_percent': 12}]}
            adapter._pve_cache.snapshot(wait=True)
            status, _, body = self.get(server, '/pve-current')
            self.assertEqual(status, 200)
            self.assertEqual(body['pve']['fetched_at'], 128)
            self.assertEqual(body['pve']['nodes'][0]['cpu_percent'], 12)
            self.assertEqual(upstream.call_count, 2)


if __name__ == '__main__':
    unittest.main()
