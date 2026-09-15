import unittest
from unittest.mock import patch
import proxmox


class NodeHistoryWindowTests(unittest.TestCase):
    def test_wallclock_clipping_fixed_domain_and_cpu_gaps(self):
        rows = [dict(time=t, cpu=.5, netin=10, netout=20)
                for t in (1199, 1200, 1260, 1380, 1440, 3001)]
        with patch.object(proxmox.time, 'time', return_value=3000):
            result = proxmox._history(rows)
        h = result['history']
        self.assertEqual((h['start_time'], h['end_time'], h['duration_seconds'], h['window']),
                         (1200, 3000, 1800, '30m'))
        self.assertEqual(h['samples'], 4)
        self.assertEqual(h['cpu_segments'], ['0,15 3.33333,15', '10,15 13.3333,15'])
        self.assertEqual(h['net_rx_segments'], ['0,15 3.33333,15', '10,15 13.3333,15'])
        self.assertIsNone(h.get('cpu_points'))
        self.assertIsNone(result['net_in_bytes_sec'])  # old RRD is not current traffic


if __name__ == '__main__':
    unittest.main()
