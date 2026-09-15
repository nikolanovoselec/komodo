import importlib
import unittest
from unittest.mock import patch


def pr(number=1, state='open', author='renovate[bot]'):
    return {'number': number, 'state': state, 'user': {'login': author},
            'title': 'Update dependency', 'html_url': 'https://evil.example/',
            'updated_at': '2026-09-15T00:00:00Z'}


class RenovateTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('renovate')
        self.module._cache = None

    def test_stops_at_last_page(self):
        with patch.object(self.module, '_page', side_effect=[([pr()], True), ([pr(2)], False)]) as fetch:
            result = self.module.collect()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result['count'], 2)
        self.assertFalse(result['truncated'])

    def test_concurrent_callers_share_one_fetch(self):
        from concurrent.futures import ThreadPoolExecutor
        with patch.object(self.module, '_page', return_value=([pr()], False)) as fetch:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.module.collect(), range(16)))
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(all(r['count'] == 1 for r in results))

    def test_transport_failures_and_malformed_payloads(self):
        import io
        from unittest.mock import Mock
        for status, body in [(403, b'{}'), (429, b'{}'), (302, b'[]'),
                             (200, b'not-json'), (200, b'{}'), (200, b'[null]')]:
            with self.subTest(status=status, body=body):
                self.module._cache = None
                response = io.BytesIO(body)
                response.status = status
                response.headers = {}
                opener = Mock()
                opener.open.return_value = response
                with patch('urllib.request.build_opener', return_value=opener):
                    self.assertIn('error', self.module.collect())

    def test_second_page_failure_discards_partial_count(self):
        with patch.object(self.module, '_page', side_effect=[([pr()], True), OSError()]):
            result = self.module.collect()
        self.assertIn('error', result)
        self.assertIsNone(result['count'])

    def test_protected_token_only_enters_fixed_github_request(self):
        import io
        from unittest.mock import Mock
        response = io.BytesIO(b'[]'); response.status = 200; response.headers = {}
        opener = Mock(); opener.open.return_value = response
        with patch.dict('os.environ', {'DYNACAT_GITHUB_TOKEN': 'test-only-secret'}), patch('urllib.request.build_opener', return_value=opener):
            result = self.module.collect()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-secret')
        self.assertTrue(request.full_url.startswith('https://api.github.com/repos/nikolanovoselec/komodo/pulls?'))
        self.assertNotIn('test-only-secret', str(result))

    def test_public_request_and_link_pagination(self):
        import io
        from unittest.mock import Mock
        response = io.BytesIO(b'[]')
        response.status = 200
        response.headers = {'Link': '<https://evil.example/>; rel="next"'}
        opener = Mock()
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            rows, more = self.module._page(2)
        self.assertEqual(rows, [])
        self.assertTrue(more)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.github.com/repos/nikolanovoselec/komodo/pulls?state=open&per_page=100&page=2')
        self.assertIsNone(request.get_header('Authorization'))
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(self.module._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_errors_are_explicit_and_cached(self):
        with patch.object(self.module, '_page', side_effect=OSError('network secret')) as fetch:
            result = self.module.collect()
            self.assertIn('error', result)
            self.assertIsNone(result['count'])
            self.assertIsNone(result['prs'])
            self.assertFalse(result['truncated'])
            self.assertNotIn('secret', str(result))
            self.module.collect()
            self.assertEqual(fetch.call_count, 1)

    def test_malformed_number_cannot_become_link(self):
        with patch.object(self.module, '_page', return_value=([pr('../evil')], False)):
            self.assertIn('error', self.module.collect())

    def test_cache_ttl_and_result_isolation(self):
        with patch.object(self.module, '_page', return_value=([pr()], False)) as fetch, \
                patch.object(self.module.time, 'monotonic', return_value=100) as clock:
            first = self.module.collect()
            first['prs'].clear()
            clock.return_value = 699
            self.assertEqual(self.module.collect()['count'], 1)
            self.assertEqual(len(self.module.collect()['prs']), 1)
            self.assertEqual(fetch.call_count, 1)
            clock.return_value = 701
            self.module.collect()
            self.assertEqual(fetch.call_count, 2)

    def test_pagination_is_bounded_and_deduplicated(self):
        with patch.object(self.module, '_page', side_effect=lambda n: ([pr(n), pr(1)], True)) as fetch:
            result = self.module.collect()
        self.assertEqual(fetch.call_count, 5)
        self.assertEqual(result['count'], 5)
        self.assertTrue(result['truncated'])

    def test_exact_filter_and_canonical_links(self):
        with patch.object(self.module, '_page', return_value=([
                pr(), pr(2, state='closed'), pr(3, author='Renovate[bot]'),
                pr(4, author='somebody')], False)):
            result = self.module.collect()
        self.assertEqual(result['count'], 1)
        self.assertFalse(result['truncated'])
        self.assertEqual(result['prs'][0]['url'], 'https://github.com/nikolanovoselec/komodo/pull/1')
        self.assertNotIn('total', result)
        self.assertNotIn('error', result)


if __name__ == '__main__':
    unittest.main()
