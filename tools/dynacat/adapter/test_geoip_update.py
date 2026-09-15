"""Database updater never receives or queries viewer addresses."""
import gzip
import importlib.util
import io
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class UpdateTests(unittest.TestCase):
    def test_download_is_bounded_validated_and_atomically_published(self):
        self.assertIsNotNone(importlib.util.find_spec('geoip_update'), 'updater must exist')
        from geoip_update import update_database
        reader = MagicMock()
        reader.__enter__.return_value = reader
        reader.metadata.return_value.database_type = 'DBIP-City-Lite'
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'dbip-city-lite.mmdb'
            target.write_bytes(b'old')
            urls = []
            def fetch(request, timeout):
                self.assertEqual(request.get_header('User-agent'), 'dynacat-geoip/1.0')
                urls.append(request.full_url)
                return io.BytesIO(gzip.compress(b'new database'))
            with patch('maxminddb.open_database', return_value=reader):
                result = update_database(directory, '2026-09', fetch=fetch)
            self.assertEqual(target.read_bytes(), b'new database')
            self.assertEqual(result, 'updated')
            self.assertEqual(urls, ['https://download.db-ip.com/free/dbip-city-lite-2026-09.mmdb.gz'])
            self.assertEqual(list(pathlib.Path(directory).glob('*.tmp')), [])


    def test_bad_month_oversize_or_corrupt_download_preserves_previous_database(self):
        from geoip_update import update_database
        import inspect
        self.assertIn('compressed_limit', inspect.signature(update_database).parameters)
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'dbip-city-lite.mmdb'
            target.write_bytes(b'known good')
            for payload, limits, error in [(b'garbage', {}, gzip.BadGzipFile), (b'x' * 50, {'compressed_limit': 20}, ValueError),
                                    (gzip.compress(b'x' * 50), {'expanded_limit': 20}, ValueError)]:
                with self.assertRaises(error):
                    update_database(directory, '2026-09', fetch=lambda *a, **k: io.BytesIO(payload), **limits)
                self.assertEqual(target.read_bytes(), b'known good')
                self.assertEqual(list(pathlib.Path(directory).glob('*.tmp')), [])
            fetch = MagicMock(return_value=io.BytesIO(b'garbage'))
            for month in ['2026-13', '../other', '2026-9', 'https://elsewhere']:
                with self.assertRaises(ValueError):
                    update_database(directory, month, fetch=fetch)
            fetch.assert_not_called()


    def test_current_database_skips_network_and_timeout_preserves_old(self):
        from geoip_update import update_database
        reader = MagicMock()
        reader.__enter__.return_value = reader
        reader.metadata.return_value.database_type = 'DBIP-City-Lite'
        reader.metadata.return_value.build_epoch = 1788226681
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'dbip-city-lite.mmdb'
            target.write_bytes(b'valid')
            fetch = MagicMock(return_value=io.BytesIO(gzip.compress(b'new database')))
            with patch('maxminddb.open_database', return_value=reader):
                self.assertEqual(update_database(directory, '2026-09', fetch=fetch), 'current')
            fetch.assert_not_called()
            fetch.side_effect = TimeoutError
            with self.assertRaises(TimeoutError):
                update_database(directory, '2026-08', fetch=fetch)
            self.assertEqual(target.read_bytes(), b'valid')


    def test_cli_rejects_invalid_month_without_traceback(self):
        import subprocess, sys
        import geoip_update
        result = subprocess.run([sys.executable, geoip_update.__file__, '--month', '../bad'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Database update failed', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_deadline_and_redirect_are_enforced(self):
        import geoip_update
        self.assertTrue(hasattr(geoip_update, 'NoRedirect'))
        with self.assertRaises(ValueError):
            geoip_update.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere')
        with tempfile.TemporaryDirectory() as directory:
            with patch('geoip_update.time.monotonic', side_effect=[0, 181]):
                with self.assertRaises(TimeoutError):
                    geoip_update.update_database(directory, '2026-09', fetch=lambda *a, **k: io.BytesIO(b'x'))


if __name__ == '__main__':
    unittest.main()
