import unittest
from workload_history import chart

class AreaTests(unittest.TestCase):
    def test_area_closes_each_real_segment_without_changing_line(self):
        result = chart([(8200,20),(8260,40),(8320,None),(8380,60),(8440,80),(8700,10)],10000)
        self.assertEqual(result['path'], 'M0.000,24.000 L3.333,18.000 M10.000,12.000 L13.333,6.000 M27.778,27.000')
        self.assertEqual(result['area_path'], 'M0.000,24.000 L3.333,18.000 L3.333,30.000 L0.000,30.000 Z M10.000,12.000 L13.333,6.000 L13.333,30.000 L10.000,30.000 Z M27.778,27.000 L27.778,30.000 L27.778,30.000 Z')
        self.assertEqual(result['samples'],5)
        self.assertEqual(result['window_seconds'],1800)

if __name__ == '__main__': unittest.main()
