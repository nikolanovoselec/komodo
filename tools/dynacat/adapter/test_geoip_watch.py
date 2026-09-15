"""Maintenance remains supervised; health validation never fetches data."""
import threading,unittest
from unittest.mock import patch,MagicMock
import geoip_update
class WatchTests(unittest.TestCase):
    def test_watch_performs_work_and_can_stop(self):
        stop=threading.Event();calls=[];messages=[]
        def update(directory,month):
            calls.append((directory,month));stop.set();return 'current'
        self.assertTrue(hasattr(geoip_update,'watch_database'))
        geoip_update.watch_database('/db','2026-09',stop=stop,updater=update,emit=messages.append)
        self.assertEqual(calls,[('/db','2026-09')]);self.assertEqual(messages,['Database current'])
    def test_health_check_is_offline_and_month_specific(self):
        self.assertTrue(hasattr(geoip_update,'database_current'))
        reader=MagicMock();reader.__enter__.return_value=reader
        reader.metadata.return_value=type('Meta',(),{'database_type':'DBIP-City-Lite','build_epoch':1788226681})()
        with patch('maxminddb.open_database',return_value=reader),patch.object(geoip_update.OPENER,'open',side_effect=AssertionError('Network forbidden')):
            self.assertTrue(geoip_update.database_current('/db','2026-09'))
            self.assertFalse(geoip_update.database_current('/db','2026-08'))
    def test_watch_redacts_failure_and_retries_on_schedule(self):
        self.assertTrue(hasattr(geoip_update,'watch_database'))
        class Stop:
            calls=0
            def is_set(self):return self.calls>=2
            def wait(self,seconds):self.calls+=1;assert seconds==3600
        messages=[]
        with patch.object(geoip_update,'update_database',side_effect=[ValueError('SECRET SOURCE'), 'current']) as update:
            geoip_update.watch_database('/db','2026-09',stop=Stop(),updater=update,emit=messages.append)
        self.assertEqual(update.call_count,2);self.assertNotIn('SECRET',str(messages));self.assertEqual(messages[-1],'Database current')
if __name__=='__main__':unittest.main()
