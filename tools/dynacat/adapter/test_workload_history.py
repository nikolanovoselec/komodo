import unittest
import tempfile
from pathlib import Path
import workload_history as h

class HistoryTests(unittest.TestCase):
    def test_exact_thirty_second_gap_breaks_collected_samples(self):
        chart = h.chart([(1900, 10), (1929, 20), (1959, 30)], now=2000, gap=30)
        self.assertEqual(chart['path'].count('M'), 2)
        self.assertEqual(chart['path'].count('L'), 1)

    def test_fixed_window_gaps_and_honest_scale(self):
        chart = h.chart([(100, 9), (1800, 50), (1860, None), (1920, 110), (1980, 120), (2100, 40)], now=2000)
        self.assertEqual(chart['samples'], 3)
        self.assertEqual(chart['scale'], 120)
        self.assertEqual(chart['path'].count('M'), 2)
        self.assertEqual(chart['start'], 200)
        self.assertEqual(chart['end'], 2000)
        self.assertNotIn('L0', chart['path'])

class StoreTests(unittest.TestCase):
    def test_locked_database_falls_back_with_short_timeout(self):
        import sqlite3
        import time
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d)/'locked.sqlite')
            store = h.Store(path)
            blocker = sqlite3.connect(path)
            blocker.execute('BEGIN EXCLUSIVE')
            try:
                start = time.monotonic()
                store.add('guest', 'ram', 1990, 40, 2000)
                self.assertLess(time.monotonic()-start, .3)
                self.assertEqual(store.state, 'unavailable')
                self.assertEqual(store.rows('guest', 'ram', 2000), [(1990, 40)])
            finally:
                blocker.rollback()
                blocker.close()

    def test_read_failure_preserves_session_samples_and_remains_usable(self):
        store = h.Store()
        store.add('guest', 'ram', 1990, 40, 2000)
        store.db.close()
        self.assertEqual(store.rows('guest', 'ram', 2000), [(1990, 40)])
        self.assertEqual(store.state, 'unavailable')
        store.add('guest', 'ram', 1995, 50, 2000)
        self.assertEqual(store.rows('guest', 'ram', 2000), [(1990, 40), (1995, 50)])

    def test_read_only_rows_falls_back(self):
        store = h.Store()
        store.add('guest', 'ram', 1990, 40, 2000)
        store.db.execute('PRAGMA query_only=ON')
        self.assertEqual(store.rows('guest', 'ram', 2000), [(1990, 40)])
        self.assertEqual(store.state, 'unavailable')

    def test_runtime_write_failure_preserves_current_telemetry(self):
        from unittest.mock import patch
        store = h.Store()
        store.db.execute('PRAGMA query_only=ON')
        guest = dict(id=1, type='qemu', node='node', status='stopped',
                     ram={'percent': 30}, memory_source='Komodo',
                     metric_binding='server|endpoint', metric_sample_ts=1990)
        with patch('workload_history.time.time', return_value=2000):
            result = h.enrich({'guest_inventory': [guest]}, api=lambda p: [], store=store)
        self.assertEqual(result['guest_inventory'][0]['ram']['percent'], 30)
        self.assertEqual(guest['history']['ram']['samples'], 1)
        self.assertEqual(guest['history']['ram']['persistence_state'], 'unavailable')
        self.assertEqual(store.rows('qemu/1|server|endpoint', 'ram', 2000), [(1990, 30)])

    def test_persistent_identity_source_separation_deduplication_and_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d)/'history.sqlite')
            store = h.Store(path)
            store.add('qemu/131|server-A|endpoint-A', 'ram', 1900, 20, now=2000)
            store.add('qemu/131|server-A|endpoint-A', 'ram', 1900, 20, now=2000)
            store.add('qemu/131|server-A|endpoint-A', 'ram', 1, 99, now=2000)
            again = h.Store(path)
            self.assertEqual(again.rows('qemu/131|server-A|endpoint-A','ram',2000), [(1900,20)])
            self.assertEqual(again.rows('qemu/131|server-B|endpoint-A','ram',2000), [])
            self.assertEqual(again.rows('qemu/131|server-A|endpoint-A','disk',2000), [])
            self.assertEqual(again.rows('qemu/131|server-A|endpoint-A','ram',4000), [])

class BackgroundTests(unittest.TestCase):
    def test_bounded_singleflight_and_failure_retry_cooldown(self):
        import threading
        entered = threading.Barrier(3)
        release = threading.Event()
        reads = []
        now = [0]
        def read(path):
            reads.append(path)
            entered.wait(2)
            release.wait(2)
            raise OSError('unavailable')
        cache = h.BackgroundRRD(read, clock=lambda: now[0])
        try:
            cache('a')
            cache('b')
            entered.wait(2)
            for _ in range(20):
                cache('a')
                cache('b')
                cache('c')
            self.assertCountEqual(reads, ['a', 'b'])
            release.set()
            with cache.condition:
                self.assertTrue(cache.condition.wait_for(lambda: not cache.inflight, 2))
            cache('a')
            self.assertCountEqual(reads, ['a', 'b'])
            now[0] = 60
            cache.read = lambda path: reads.append(path) or [dict(time=1950, cpu=.5)]
            cache('a')
            with cache.condition:
                self.assertTrue(cache.condition.wait_for(lambda: not cache.inflight, 2))
            self.assertEqual(cache('a'), [dict(time=1950, cpu=.5)])
            self.assertEqual(reads.count('a'), 2)
        finally:
            release.set()
            cache.executor.shutdown(wait=True)


    def test_stopped_guests_do_not_schedule_rrd_reads(self):
        reads = []
        guest = dict(id=1, type='qemu', node='node', status='stopped')
        h.enrich({'guest_inventory': [guest]}, api=lambda p: reads.append(p) or [], store=h.Store())
        self.assertEqual(reads, [])

    def test_blocked_guest_history_does_not_delay_current_or_node_snapshot(self):
        import threading
        import proxmox
        from unittest.mock import patch
        entered, release, current_done, node_done = [threading.Event() for _ in range(4)]
        def read(path, **kwargs):
            if '/qemu/' in path:
                entered.set()
                release.wait(3)
                return []
            if path == '/nodes':
                return [dict(node='node', status='online', cpu=.2)]
            return []
        result = {'guest_inventory': [dict(id=1, type='qemu', node='node', status='running')]}
        def current():
            h.enrich(result, store=h.Store())
            current_done.set()
        def node():
            proxmox.collect()
            node_done.set()
        with patch.object(proxmox, '_api', read), patch.object(proxmox, '_cached_api', proxmox.SlowReadCache(read)):
            t = threading.Thread(target=current)
            t.start()
            try:
                self.assertTrue(entered.wait(1))
                n = threading.Thread(target=node)
                n.start()
                self.assertTrue(current_done.wait(.2), 'guest RRD blocked current telemetry')
                self.assertTrue(node_done.wait(.2), 'guest RRD holds physical-node cache lock')
            finally:
                release.set()
                t.join(2)
                if 'n' in locals(): n.join(2)

class IntegrationTests(unittest.TestCase):
    def test_guest_rrd_binding_and_enriched_memory_sources_stay_separate(self):
        import proxmox
        from unittest.mock import patch
        guest = dict(id=131,type='qemu',node='proxmox-iii',status='running',cpu_percent=20,
                     ram={'percent':30},disk={'percent':40},memory_source='Komodo',disk_source='Komodo',
                     metric_sample_ts=1990, metric_binding='server-A|endpoint-A')
        result = {'guest_inventory':[guest], 'fetched_at':2000}
        reads=[]
        def api(path):
            reads.append(path)
            return [dict(time=1950,cpu=.5,mem=110,maxmem=100,disk=0,maxdisk=100)]
        with patch('workload_history.time.time', return_value=2000):
            h.enrich(result, api=api, store=h.Store())
        self.assertEqual(reads,['/nodes/proxmox-iii/qemu/131/rrddata?timeframe=hour&cf=AVERAGE'])
        self.assertEqual(guest['history']['cpu']['samples'],1)
        self.assertEqual(guest['history']['ram']['samples'],1)
        self.assertEqual(guest['history']['ram']['dots'][0]['y'],21)
        self.assertEqual(guest['history']['ram']['source'],'Komodo / Periphery · collected samples')
        self.assertEqual(guest['history']['disk']['samples'],1)

    def test_production_wiring(self):
        root = Path(__file__).parent
        self.assertIn('workload_history.enrich', (root/'adapter.py').read_text())
        self.assertIn('metric_binding', (root/'vm_metrics.py').read_text())
        self.assertIn('MEDIA_HISTORY_PATH', (root/'media.py').read_text())
        config = (root.parent/'config/dynacat.yml').read_text()
        self.assertIn('cw-history-chart',config)
        self.assertNotIn('history.cpu_points',config)
        self.assertNotIn('ten-minute window',config)

class SourcesTests(unittest.TestCase):
    def test_rrd_never_substitutes_vm_disk_or_io_and_retains_host_ram(self):
        rows = [dict(time=1950, cpu=.25, mem=110, maxmem=100, disk=50, maxdisk=100, diskwrite=999)]
        vm = h.rrd(rows, 'qemu')
        self.assertEqual(vm['cpu'], [(1950,25)])
        self.assertEqual(vm['ram'], [(1950,110)])
        self.assertEqual(vm['disk'], [(1950,None)])
        self.assertEqual(h.rrd(rows, 'lxc')['disk'], [(1950,50)])

if __name__ == '__main__': unittest.main()
