"""Response-time freshness must not rewrite cached samples or history."""
import copy
import unittest
from unittest.mock import Mock, patch
import media


class CurrentTrafficTests(unittest.TestCase):
    def test_cached_sample_expires_at_boundary_without_mutation(self):
        history = media.TrafficHistory()
        traffic = history.observe(dict(refresh_ts=100000, polling_rate='5-sec',
                                       network_ingress_bytes=125000, network_egress_bytes=250000), now=101)
        cached = dict(data=dict(traffic=traffic, servers=[]), age=8, state='ready')
        original = copy.deepcopy(cached)
        points = copy.deepcopy(list(history.points))
        sources = {name: Mock(snapshot=Mock(return_value=cached if name == 'resources' else {}))
                   for name in ('sessions', 'resources', 'qbittorrent')}
        with patch.dict(media.SOURCES, sources), patch.object(media.time, 'time', return_value=129.9):
            fresh = media.current('current')['resources']['data']['traffic']
        self.assertAlmostEqual(fresh['age_seconds'], 29.9)
        self.assertTrue(fresh['available'])
        with patch.dict(media.SOURCES, sources), patch.object(media.time, 'time', return_value=130):
            stale = media.current('current')['resources']['data']['traffic']
        self.assertEqual(stale['state'], 'stale')
        self.assertFalse(stale['available'])
        self.assertIsNone(stale['rx_mbps'])
        self.assertIsNone(stale['tx_mbps'])
        self.assertEqual(stale['graph'], traffic['graph'])
        self.assertEqual(stale['points'], traffic['points'])
        self.assertEqual(cached, original)
        self.assertEqual(list(history.points), points)

    def test_unknown_age_and_interval_have_explicit_presence_flags(self):
        for stats, has_age, has_interval in [({}, False, False),
                (dict(refresh_ts=100000, polling_rate='5-sec', network_ingress_bytes=0, network_egress_bytes=0), True, True)]:
            traffic = media.TrafficHistory().observe(stats, now=100)
            self.assertEqual(traffic.get('has_age'), has_age)
            self.assertEqual(traffic.get('has_interval'), has_interval)
        from pathlib import Path
        template = (Path(__file__).resolve().parents[1] / 'config/dynacat.yml').read_text()
        self.assertNotIn('age unknown', template)
        self.assertNotIn('source interval', template)
        self.assertIn('Data unavailable', template)
        self.assertIn('Data is stale', template)
        self.assertNotIn('s + collection', template)

    def test_invalid_sample_time_and_empty_resources(self):
        for ts in (None, 0, -1, 131, float('nan'), float('inf'), '100', True):
            with self.subTest(ts=ts):
                cached = dict(data=dict(traffic=dict(sample_ts=ts, available=True, state='ready',
                                                    rx_mbps=1, tx_mbps=2)), age=0)
                sources = {name: Mock(snapshot=Mock(return_value=cached if name == 'resources' else {}))
                           for name in ('sessions', 'resources', 'qbittorrent')}
                with patch.dict(media.SOURCES, sources), patch.object(media.time, 'time', return_value=130):
                    result = media.current('current')['resources']['data']['traffic']
                self.assertEqual(result['state'], 'unavailable')
                self.assertFalse(result['available'])
                self.assertIsNone(result['age_seconds'])
                self.assertIsNone(result['rx_mbps'])
                self.assertIsNone(result['tx_mbps'])
        for data in ({}, None):
            sources['resources'].snapshot.return_value = dict(data=data, state='starting')
            with patch.dict(media.SOURCES, sources):
                self.assertEqual(media.current('current')['resources']['data'], data)
