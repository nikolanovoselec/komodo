import unittest
from media_traffic import TrafficHistory


def sample(ts=100000, rx=5_000_000, tx=2_500_000, interval='5-sec'):
    return dict(refresh_ts=ts, network_ingress_bytes=rx,
                network_egress_bytes=tx, polling_rate=interval)


class TrafficHistoryTests(unittest.TestCase):
    def test_interval_volume_is_normalized_to_decimal_mbps(self):
        result = TrafficHistory().observe(sample(), now=100)
        self.assertEqual(result['rx_mbps'], 8)
        self.assertEqual(result['tx_mbps'], 4)
        self.assertEqual(result['interval_seconds'], 5)
        self.assertTrue(result['warmup'])
        self.assertEqual(result['points'], [{'ts': 100.0, 'rx_mbps': 8.0, 'tx_mbps': 4.0}])

    def test_history_preserves_only_real_unique_fresh_samples(self):
        history = TrafficHistory(max_points=4, window_seconds=60)
        first = history.observe(sample(), now=100)
        duplicate = history.observe(sample(), now=101)
        self.assertEqual(duplicate['points'], first['points'])
        self.assertEqual(duplicate['age_seconds'], 1)
        lower = history.observe(sample(105000, rx=500000, tx=0), now=105)
        self.assertEqual(lower['rx_mbps'], .8)  # falling interval volumes are not counter resets
        self.assertEqual(lower['tx_mbps'], 0)
        self.assertFalse(lower['warmup'])
        core_sample = history.observe(sample(120000), now=120)
        self.assertEqual(len(core_sample['points']),3)  # Core publishes ~15s, Periphery measures 5s
        self.assertEqual(core_sample['rx_mbps'],8)  # retain 5s interval normalization
        skipped = history.observe(sample(160000), now=160)
        self.assertIsNone(skipped['points'][-2]['rx_mbps'])
        self.assertEqual(skipped['rx_mbps'], 8)
        stale = history.observe(sample(160000), now=191)
        self.assertFalse(stale['available'])
        self.assertEqual(stale['state'], 'stale')
        self.assertIsNone(stale['rx_mbps'])
        self.assertIsNone(stale['points'][-1]['tx_mbps'])
        self.assertLessEqual(len(stale['points']), 4)
        expired = history.observe({}, now=300)
        self.assertEqual(expired['points'], [])
        self.assertEqual(expired['state'], 'unavailable')

    def test_invalid_empty_future_negative_and_nonfinite_are_null(self):
        for stats in ({}, None, sample(rx=-1), sample(tx=float('nan')),
                      sample(rx=True), sample(ts=101000), sample(ts=None),
                      sample(interval='unknown'), sample(interval='0-sec')):
            with self.subTest(stats=stats):
                result = TrafficHistory().observe(stats, now=100)
                self.assertFalse(result['available'])
                self.assertIsNone(result['rx_mbps'])
                self.assertEqual(result['points'], [])

    def test_configured_interval_is_not_assumed_five_seconds(self):
        result = TrafficHistory().observe(sample(interval='1-min'), now=100)
        self.assertAlmostEqual(result['rx_mbps'], 2/3)
        self.assertEqual(result['interval_seconds'], 60)

    def test_timestamp_reset_clears_old_epoch_and_warms_up(self):
        history = TrafficHistory()
        history.observe(sample(), now=100)
        history.observe(sample(105000), now=105)
        result = history.observe(sample(101000), now=106)
        self.assertTrue(result['warmup'])
        self.assertEqual([p['ts'] for p in result['points']], [101])

    def test_missing_read_then_same_sample_never_bridges_gap(self):
        history = TrafficHistory()
        history.observe(sample(), now=100)
        history.observe({}, now=101)
        result = history.observe(sample(), now=102)
        self.assertEqual(len(result['points']), 2)
        self.assertIsNone(result['points'][-1]['rx_mbps'])
        result = history.observe(sample(105000), now=105)
        self.assertEqual([p['ts'] for p in result['points']], [100, 101, 105])


if __name__ == '__main__':
    unittest.main()
