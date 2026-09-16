"""Display-only smooth interpolation; synthetic edge cases explicitly labelled."""
import copy
import re
import unittest
import pihole


def history(values, stamps=None, now=2400):
    stamps = stamps or [900, 1500, 2100]
    rows = [{'history': [dict(timestamp=t, total=v, blocked=v//2) for t,v in zip(stamps,values) if v is not None]} for _ in range(2)]
    return pihole.query_history(rows, now, window_seconds=1800)


class SmoothTests(unittest.TestCase):
    def test_native_tooltip_labels_interpolation_and_exact_counts(self):
        from pathlib import Path
        template = (Path(__file__).resolve().parents[1]/'config/dynacat.yml').read_text()
        self.assertIn('Smooth display interpolation', template)
        self.assertIn('10-minute query counts, UTC', template)
        self.assertIn('pihole.query_history.start', template)
        self.assertIn('pihole.query_history.end', template)

    def test_native_template_uses_curve_fields(self):
        from pathlib import Path
        template = (Path(__file__).resolve().parents[1]/'config/dynacat.yml').read_text()
        for key in ('total', 'blocked'):
            self.assertIn(f'pihole.query_history.{key}.curve_path', template)
            self.assertIn(f'pihole.query_history.{key}.curve_area_path', template)

    def test_synthetic_missing_and_null_bins_remain_separate_closed_segments(self):
        for h in (history([10,None,30]), history([10,30], [900,2100])):
            self.assertEqual(h['total']['curve_path'].count('M'), 2)
            self.assertEqual(h['total']['curve_area_path'].count(' Z'), 2)
            self.assertEqual(h['missing_spans'], [dict(start_epoch=1200,end_epoch=1800,x=200.0,width=200.0)])
        rows = [{'history':[dict(timestamp=t,total=10,blocked=2) for t in (900,1500,2100)]},
                {'history':[dict(timestamp=t,total=10,blocked=2) for t in (900,2100)]}]
        self.assertEqual(pihole.query_history(rows,2400)['total']['curve_path'].count('M'),2)

    def test_synthetic_clipped_partial_bin_and_zero(self):
        h=history([0,0,0,0],[300,900,1500,2100],now=2250)
        self.assertEqual(h['end_epoch']-h['start_epoch'],1800)
        self.assertTrue(h['total']['curve_path'].startswith('M0.000000,140.000000'))
        self.assertTrue(h['total']['curve_path'].endswith('600.000000,140.000000'))
        self.assertEqual(history([])['total']['curve_path'],'')

    def test_synthetic_random_curves_have_no_overshoot_and_continuous_tangents(self):
        import random
        rng=random.Random(4)
        for _ in range(150):
            h=history([rng.randrange(10000) for _ in range(4)],[300,900,1500,2100],now=2250)
            path=h['total']['curve_path']
            chunks=path.split(' C')
            x,y=map(float,chunks[0][1:].split(','))
            previous_slope=None
            for chunk in chunks[1:]:
                a,b,c,d,nx,ny=map(float,re.findall(r'-?\d+\.\d+',chunk))
                slope=(b-y)/(a-x)
                if previous_slope is not None:self.assertAlmostEqual(slope,previous_slope,places=5)
                previous_slope=(ny-d)/(nx-c)
                for step in range(101):
                    t=step/100
                    yy=(1-t)**3*y+3*(1-t)**2*t*b+3*(1-t)*t*t*d+t**3*ny
                    self.assertGreaterEqual(yy,min(y,ny)-1e-6)
                    self.assertLessEqual(yy,max(y,ny)+1e-6)
                x,y=nx,ny

    def test_synthetic_curve_is_bounded_and_hits_bin_midpoints(self):
        h = history([1, 100, 0])
        path = h['total'].get('curve_path', h['total']['bin_path'])
        self.assertIn(' C', path, 'activity must use continuous cubic curves, not steps')
        self.assertNotIn(' L', path)
        self.assertTrue(path.startswith('M0.000000,138.600000'))
        self.assertTrue(path.endswith('600.000000,140.000000'))
        for x,y in [(100,138.6),(300,0),(500,140)]:
            self.assertIn(f'{x:.6f},{y:.6f}',path)
        nums = [float(x) for x in re.findall(r'-?\d+\.\d+',path)]
        for x,y in zip(nums[::2],nums[1::2]):
            self.assertTrue(0 <= x <= 600)
            self.assertTrue(0 <= y <= 140)
        self.assertEqual(h['total']['curve_area_path'].count(' Z'),1)


if __name__ == '__main__': unittest.main()
