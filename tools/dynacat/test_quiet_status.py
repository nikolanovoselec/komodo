"""Routine polling diagnostics must not compete with dashboard data."""
import unittest
from pathlib import Path
class QuietStatus(unittest.TestCase):
    def test_non_arr_widgets_have_no_polling_boilerplate(self):
        text=Path(__file__).with_name('config').joinpath('dynacat.yml').read_text()
        text='\n'.join(line for line in text.splitlines() if 'mo-arr-delivery' not in line)
        for phrase in ('snapshot age','since collection','UI refresh','collector cache','PVE remains authoritative','Docker grouped only by audited guest identity','cache 5m','cache 5s','age unknown','Source: Proxmox node API','Disk: enabled reporting'):
            with self.subTest(phrase=phrase):self.assertNotIn(phrase,text)
        self.assertIn('IP Geolocation by DB-IP',text)
        self.assertIn('k-warning',text)
        self.assertIn('Data is stale',text)
if __name__=='__main__':unittest.main()
