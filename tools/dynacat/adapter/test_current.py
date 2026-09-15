"""Fast snapshot HTTP regression tests with event-controlled upstream work."""
import concurrent.futures
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import adapter


class Current(unittest.TestCase):
    def test_cold_start_failure_retry_and_recovery_are_nonblocking(self):
        clock = [0.0]
        started, release = threading.Event(), threading.Event()
        calls = []
        def load():
            calls.append(1)
            started.set()
            release.wait(3)
            if len(calls) == 2:
                raise RuntimeError('secret-token')
            return {'ok': True}
        server = adapter.make_server(('127.0.0.1', 0), load)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def get(path='/current'):
            try:
                response = urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}{path}', timeout=1)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                return response.status, json.load(response)
        try:
            with patch('adapter.time.monotonic', side_effect=lambda: clock[0]):
                status, data = get()
                self.assertEqual(status, 503)
                self.assertEqual(data['freshness']['state'], 'starting')
                self.assertTrue(started.wait(1))
                self.assertEqual(get()[0], 503)
                self.assertEqual(len(calls), 1)
                release.set()
                self.assertEqual(get('/summary')[0], 200)
                release.clear(); started.clear(); clock[0] = 5
                self.assertEqual(get()[0], 200)
                self.assertTrue(started.wait(1))
                release.set()
                self.assertEqual(get('/summary')[0], 503)
                for _ in range(4):
                    status, data = get()
                    self.assertEqual(status, 503)
                    self.assertNotIn('ok', data)
                    self.assertNotIn('secret-token', str(data))
                    self.assertEqual(data['freshness']['state'], 'unavailable')
                self.assertEqual(len(calls), 2)
                release.clear(); started.clear(); clock[0] = 10
                self.assertEqual(get()[0], 503)
                self.assertTrue(started.wait(1))
                self.assertEqual(get()[0], 503)
                release.set()
                self.assertEqual(get('/summary')[0], 200)
                self.assertEqual(get()[1]['freshness']['state'], 'cached')
                self.assertEqual(len(calls), 3)
        finally:
            release.set()
            server.shutdown(); server.server_close(); thread.join()

    def test_expired_samples_fail_closed_even_while_collection_is_running(self):
        clock = [0.0]
        release = threading.Event()
        calls = []
        def load():
            calls.append(1)
            if len(calls) > 1:
                release.wait(3)
            return {'ok': True}
        server = adapter.make_server(('127.0.0.1', 0), load)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def get(path):
            try:
                response = urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}{path}', timeout=1)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)
        try:
            with patch('adapter.time.monotonic', side_effect=lambda: clock[0]):
                self.assertEqual(get('/summary')[0], 200)
                clock[0] = 5
                self.assertEqual(get('/current')[0], 200)
                clock[0] = 30
                status, data = get('/current')
                self.assertEqual(status, 503)
                self.assertNotIn('ok', data)
                self.assertEqual(data['freshness']['state'], 'expired')
                self.assertTrue(data['freshness']['collecting'])
                self.assertEqual(data['freshness']['max_age_seconds'], 30)
                self.assertEqual(len(calls), 2)
                # A late completion cannot make an already-old snapshot fresh.
                clock[0] = 40
                release.set()
                self.assertEqual(get('/summary')[0], 503)
                self.assertEqual(get('/current')[0], 503)
        finally:
            release.set()
            server.shutdown(); server.server_close(); thread.join()

    def test_current_is_fast_during_summary_refresh_and_single_flight(self):
        clock = [0.0]
        started, release = threading.Event(), threading.Event()
        calls = []
        def load():
            calls.append(1)
            if len(calls) == 2:
                started.set()
                release.wait(3)
            return {'generation': len(calls)}
        server = adapter.make_server(('127.0.0.1', 0), load)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def get(path):
            try:
                response = urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}{path}', timeout=1)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response) if response.status != 404 else {}
        try:
            with patch('adapter.time.monotonic', side_effect=lambda: clock[0]):
                self.assertEqual(get('/summary'), (200, {'generation': 1}))
                clock[0] = 5
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pending = pool.submit(get, '/summary')
                    self.assertTrue(started.wait(1))
                    try:
                        for _ in range(4):
                            status, data = get('/current')
                            self.assertEqual(status, 200)
                            self.assertEqual(data['generation'], 1)
                            self.assertEqual(data['freshness']['state'], 'collecting')
                            self.assertEqual(data['freshness']['age_seconds'], 5)
                        self.assertEqual(len(calls), 2)
                    finally:
                        release.set()
                    self.assertEqual(pending.result(), (200, {'generation': 2}))
        finally:
            release.set()
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
