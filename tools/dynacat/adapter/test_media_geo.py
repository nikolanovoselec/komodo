"""Offline geolocation tests; all addresses here are synthetic fixtures."""
import importlib.util
import pathlib
import unittest


class GeoTests(unittest.TestCase):
    def test_nonpublic_and_missing_addresses_are_honest(self):
        self.assertIsNotNone(importlib.util.find_spec('media_geo'), 'offline module must exist')
        from media_geo import GeoLocator
        geo = GeoLocator('/nonexistent/db.mmdb')
        for address in ['192.168.1.2', '127.0.0.1', '100.64.0.1', '::1', 'fc00::1', '224.0.0.1', '192.0.2.1']:
            self.assertEqual(geo.locate(address)['label'], 'Local network')
        for address in ['', None, 'not-an-ip']:
            self.assertEqual(geo.locate(address)['label'], 'Location unknown')
        self.assertEqual(geo.locate('8.8.8.8')['label'], 'Location unavailable')

    def test_public_lookup_projects_only_approximate_city_country(self):
        from unittest.mock import patch, MagicMock
        from media_geo import GeoLocator
        reader = MagicMock()
        reader.__enter__.return_value = reader
        reader.get.return_value = {'city': {'names': {'en': 'Mountain View'}},
                                   'country': {'names': {'en': 'United States'}},
                                   'location': {'latitude': 37.4}}
        with patch('maxminddb.open_database', return_value=reader):
            geo = GeoLocator(__file__)
            result = geo.locate('8.8.8.8')
            self.assertEqual(result['label'], '≈ Mountain View, United States')
            self.assertEqual(result['status'], 'approximate')
            self.assertNotIn('latitude', str(result))
            self.assertNotIn('8.8.8.8', str(result))


    def test_reader_is_cached_but_reopened_after_atomic_database_replacement(self):
        from unittest.mock import patch, MagicMock
        from media_geo import GeoLocator
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            db = pathlib.Path(directory) / 'city.mmdb'
            db.write_bytes(b'first')
            reader = MagicMock()
            reader.get.return_value = {'country': {'names': {'en': 'United States'}}}
            reader.__enter__.return_value = reader
            with patch('maxminddb.open_database', return_value=reader) as opening:
                geo = GeoLocator(str(db))
                geo.locate('8.8.8.8'); geo.locate('8.8.4.4')
                self.assertEqual(opening.call_count, 1)
                updated = db.with_suffix('.new')
                updated.write_bytes(b'second')
                updated.replace(db)
                geo.locate('8.8.8.8')
                self.assertEqual(opening.call_count, 2)
                reader.close.assert_called_once()
                reader.get.side_effect = ValueError('reader error containing sensitive address')
                self.assertEqual(geo.locate('8.8.8.8')['status'], 'unavailable')


    def test_sessions_add_location_without_leaking_address_or_losing_lan_wan(self):
        from unittest.mock import patch
        import media
        items = [{'title': 'Fixture', 'Player': {'address': '192.168.1.2'}, 'Session': {'location': 'lan'}},
                 {'title': 'Fixture', 'Player': {'address': '8.8.8.8', 'relayed': True}, 'Session': {'location': 'wan'}}]
        with patch.object(media, 'plex', return_value={'Metadata': items}), patch.object(media, 'plex_machine', return_value=''):
            rows = media.sessions()['streams']
        self.assertEqual(rows[0].get('geo_label'), 'Local network')
        self.assertEqual(rows[0]['location'], 'lan')
        self.assertEqual(rows[1].get('geo_label'), 'Relay · location unknown')
        self.assertEqual(rows[1]['location'], 'wan')
        self.assertNotIn('8.8.8.8', str(rows))
        self.assertNotIn('192.168.1.2', str(rows))


if __name__ == '__main__':
    unittest.main()
