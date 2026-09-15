import unittest
from media_traffic import graph

class MediaGraphTests(unittest.TestCase):
    def test_empty(self):
        result=graph([],600)
        self.assertEqual(result['series'][0]['path'],'')
        self.assertEqual(result['samples'],0)
    def test_points_break_at_missing_not_zero(self):
        result=graph([{'ts':1000,'rx_mbps':2,'tx_mbps':1},{'ts':1005,'rx_mbps':None,'tx_mbps':None},{'ts':1010,'rx_mbps':4,'tx_mbps':2}],600)
        self.assertEqual(result['series'][0]['path'].count('M'),2)
        self.assertNotIn('L',result['series'][0]['path'])
        self.assertEqual(result['samples'],2)
        self.assertEqual(result['span_seconds'],10)
        self.assertGreaterEqual(result['scale_mbps'],4)
    def test_real_contiguous_line(self):
        result=graph([{'ts':1000,'rx_mbps':0,'tx_mbps':1},{'ts':1005,'rx_mbps':1,'tx_mbps':2}],600)
        self.assertIn('L',result['series'][0]['path'])
        self.assertEqual(len(result['series'][0]['points']),2)
