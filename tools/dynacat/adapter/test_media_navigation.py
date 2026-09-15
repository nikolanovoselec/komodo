"""Navigation projection tests; synthetic fixtures are never served."""
import json
import unittest
from unittest.mock import patch
import media


class MediaNavigationTests(unittest.TestCase):
    def test_arr_exact_api_slug_and_separate_imdb(self):
        for source, kind, slug in [('sonarr', 'series', '1883'), ('radarr', 'movie', '216527')]:
            entity = {'id': 116, 'title': 'Fixture', 'titleSlug': slug, 'imdbId': 'tt1234567'}
            payload = {'records': [{kind: entity, 'size': 100, 'sizeleft': 25}], 'totalRecords': 1}
            with patch.object(media, 'arr', return_value=payload):
                result = media.arr_data(source)
            for row in result['recent'] + result['queue']:
                self.assertEqual(row.get('url'), f'https://{source}.graymatter.ch/{kind}/{slug}')
                self.assertEqual(row['imdb'], 'https://www.imdb.com/title/tt1234567/')
                self.assertEqual(row['title'], 'Fixture')
            self.assertEqual(result['queue'][0]['progress'], 75)

    def test_arr_missing_or_unsafe_slug_never_invents_title_route(self):
        for slug in [None, '', '../secret', 'x?apikey=secret', 'https://evil', 'x#secret']:
            payload = {'records': [{'movie': {'id': 1, 'title': 'Fixture', 'titleSlug': slug}}]}
            with patch.object(media, 'arr', return_value=payload):
                result = media.arr_data('radarr')
            for row in result['recent'] + result['queue']:
                self.assertEqual(row.get('url'), '')
                self.assertNotIn('secret', json.dumps(row))

    def test_import_gallery_uses_exact_service_route(self):
        def response(source, path):
            kind = 'movie' if source == 'radarr' else 'series'
            return {'records': [{kind: {'id': 116, 'title': 'Fixture', 'titleSlug': '216527', 'imdbId': 'tt1234567'}, 'date': '2026-09-14T00:00:00Z'}]}
        with patch.object(media, 'arr', side_effect=response), patch.object(media, 'read', side_effect=ValueError):
            result = media.import_gallery()
        for row in result['recent']:
            source = row['library'].split()[0].lower()
            kind = 'movie' if source == 'radarr' else 'series'
            self.assertEqual(row.get('url'), f'https://{source}.graymatter.ch/{kind}/216527')
            self.assertEqual(row['imdb'], 'https://www.imdb.com/title/tt1234567/')

    def test_qbittorrent_exact_vuetorrent_route_and_invalid_hash_fallback(self):
        torrent_hash = '0123456789abcdef0123456789abcdef01234567'
        def response(url):
            if url.endswith('transfer/info'):
                return {'dl_info_speed': 125000, 'up_info_speed': 250000, 'connection_status': 'connected'}
            return [{'name': 'Fixture', 'hash': value, 'progress': 0.5, 'amount_left': 1000000000}
                    for value in [torrent_hash, 'private-hash', 'x?apikey=secret', None]]
        with patch.object(media, 'read', side_effect=response):
            result = media.qbittorrent()
        self.assertEqual(result.get('url'), 'https://qbittorrent.graymatter.ch/#/')
        self.assertEqual(result['downloads'][0].get('url'), result['url'] + 'torrent/' + torrent_hash)
        for row in result['downloads'][1:]:
            self.assertEqual(row.get('url'), result['url'])
        self.assertEqual(result['download_mbps'], 1)
        self.assertEqual(result['downloads'][0]['progress'], 50)
        self.assertNotIn('private-hash', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))

    def test_media_servers_link_to_existing_browser_endpoints(self):
        import adapter
        with patch.object(adapter, 'api', return_value=[]):
            rows = media.resources()['servers']
        for row in rows:
            self.assertEqual(row['url'], 'https://' + row['name'].lower() + '.novoselec.ch')
            self.assertEqual(row['container_url'], adapter.komodo_url(media.SERVER_ID, 'media_servers_' + row['name'].lower()))
            self.assertIsNone(row['cpu'])
            self.assertEqual(row['state'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
