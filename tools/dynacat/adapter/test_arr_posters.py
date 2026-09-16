"""Synthetic image fixtures; never served as live media data."""
import base64
import json
import unittest
from unittest.mock import patch
import media

JPEG = b'\xff\xd8\xff\xe0fixture'
PNG = b'\x89PNG\r\n\x1a\nfixture'
TVDB = 'https://artworks.thetvdb.com/banners/posters/123.jpg'


class ArrPosterTests(unittest.TestCase):
    def setUp(self):
        if hasattr(media, '_ARR_POSTER_CACHE'):
            media._ARR_POSTER_CACHE.clear()

    def project(self, source, entity):
        record = {'movie' if source == 'radarr' else 'series': entity,
                  'size': 100, 'sizeleft': 25, 'status': 'downloading'}
        with patch.object(media, 'arr', return_value={'records': [record], 'totalRecords': 1}):
            return media.arr_data(source)

    def test_radarr_jpeg_projects_queue_and_recent_without_credentials(self):
        with patch.dict(media.os.environ, {'RADARR_API_KEY': 'private-key'}), \
                patch.object(media, 'read', return_value=JPEG) as read:
            result = self.project('radarr', {'id': 123, 'title': 'Movie', 'titleSlug': 'movie'})
        for section in ('queue', 'recent'):
            row = result[section][0]
            self.assertEqual(row.get('poster'), base64.b64encode(JPEG).decode())
            self.assertEqual(row.get('poster_mime'), 'image/jpeg')
        self.assertEqual(result['queue'][0]['progress'], 75)
        self.assertNotIn('private-key', json.dumps(result))
        self.assertTrue(read.called)
        self.assertEqual(read.call_args.args[0], media.ARR['radarr'] + '/MediaCover/123/poster-250.jpg')
        self.assertEqual(read.call_args.args[1], {'X-Api-Key': 'private-key'})
        self.assertEqual(read.call_args.kwargs, {'binary': True, 'limit': 1_000_000})

    def test_png_signature_overrides_radarr_jpg_filename(self):
        with patch.dict(media.os.environ, {'RADARR_API_KEY': 'private-key'}), \
                patch.object(media, 'read', return_value=PNG):
            result = self.project('radarr', {'id': 123})
        for section in ('queue', 'recent'):
            self.assertEqual(result[section][0]['poster'], base64.b64encode(PNG).decode())
            self.assertEqual(result[section][0]['poster_mime'], 'image/png')

    def test_sonarr_allowlisted_remote_art_has_no_api_headers(self):
        for body, mime in ((JPEG, 'image/jpeg'), (PNG, 'image/png')):
            media._ARR_POSTER_CACHE.clear()
            with self.subTest(mime=mime), patch.object(media, 'read', return_value=body) as read:
                result = self.project('sonarr', {'id': 5, 'images': [
                    {'coverType': 'fanart', 'remoteUrl': 'https://evil.invalid/banner'},
                    {'coverType': 'poster', 'remoteUrl': TVDB}]})
                for section in ('queue', 'recent'):
                    self.assertEqual(result[section][0]['poster'], base64.b64encode(body).decode())
                    self.assertEqual(result[section][0]['poster_mime'], mime)
                read.assert_called_with(TVDB, binary=True, limit=1_000_000)

    def test_cache_reuses_until_five_minutes_then_refreshes(self):
        with patch.dict(media.os.environ, {'RADARR_API_KEY': 'private-key'}), \
                patch.object(media.time, 'monotonic', return_value=100) as clock, \
                patch.object(media, 'read', return_value=JPEG) as read:
            self.project('radarr', {'id': 123})
            clock.return_value = 399
            self.project('radarr', {'id': 123})
            self.assertEqual(read.call_count, 1)
            clock.return_value = 400
            self.project('radarr', {'id': 123})
            self.assertEqual(read.call_count, 2)

    def test_cache_evicts_at_128_entries(self):
        with patch.dict(media.os.environ, {'RADARR_API_KEY': 'private-key'}), \
                patch.object(media, 'read', return_value=JPEG) as read:
            for key in range(1, 130):
                media.arr_poster('radarr', {'id': key})
            self.assertLessEqual(len(media._ARR_POSTER_CACHE), 128)
            media.arr_poster('radarr', {'id': 1})
            self.assertEqual(read.call_count, 130)

    def test_untrusted_origins_and_paths_never_fetch(self):
        bad_urls = ('http://artworks.thetvdb.com/banners/a.jpg',
                    'https://evil.invalid/banners/a.jpg',
                    'https://artworks.thetvdb.com.evil.invalid/banners/a.jpg',
                    'https://artworks.thetvdb.com@evil.invalid/banners/a.jpg',
                    'https://user@artworks.thetvdb.com/banners/a.jpg',
                    TVDB + '?apikey=secret', TVDB + '#secret',
                    'https://artworks.thetvdb.com:443/banners/a.jpg',
                    'https://artworks.thetvdb.com/banners/../secret',
                    'https://artworks.thetvdb.com/banners/%2e%2e/secret',
                    'https://artworks.thetvdb.com/banners/a.jpg\n',
                    'https://artworks.thetvdb.com/other/a.jpg', None)
        with patch.object(media, 'read') as read:
            for url in bad_urls:
                with self.subTest(url=url):
                    self.assertEqual(media.arr_poster('sonarr', {'images': [
                        {'coverType': 'poster', 'remoteUrl': url}]}),
                        {'poster': '', 'poster_mime': ''})
            read.assert_not_called()

    def test_invalid_radarr_ids_and_missing_credentials_never_fetch(self):
        with patch.object(media, 'read') as read, patch.dict(media.os.environ, {}, clear=True):
            for key in (None, True, -1, 0, '../1', '1', '١٢٣', 1):
                self.assertEqual(media.arr_poster('radarr', {'id': key}),
                                 {'poster': '', 'poster_mime': ''})
            read.assert_not_called()

    def test_invalid_signatures_and_fetch_failures_keep_telemetry(self):
        for body in (b'<svg>secret</svg>', b'<html>secret', b'GIF89a', b'\xff\xd8', b'\x89PNG', b''):
            self.setUp()
            with self.subTest(body=body), patch.object(media, 'read', return_value=body):
                result = self.project('sonarr', {'images': [{'coverType': 'poster', 'remoteUrl': TVDB}]})
                self.assertEqual(result['queue'][0]['poster'], '')
                self.assertEqual(result['recent'][0]['poster_mime'], '')
                self.assertEqual(result['queue'][0]['progress'], 75)
                self.assertNotIn('secret', json.dumps(result))
        self.setUp()
        with patch.object(media, 'read', side_effect=TimeoutError('private-key')):
            result = self.project('sonarr', {'images': [{'coverType': 'poster', 'remoteUrl': TVDB}]})
            self.assertEqual(result['queue'][0]['poster'], '')
            self.assertEqual(result['queue'][0]['progress'], 75)
            self.assertNotIn('private-key', json.dumps(result))

    def test_real_read_enforces_one_megabyte_and_signature_not_http_type(self):
        from io import BytesIO
        for size in (1_000_000, 1_000_001):
            self.setUp()
            body = PNG + b'x' * (size - len(PNG))
            response = BytesIO(body)
            with patch.object(media.OPENER, 'open', return_value=response) as open_url:
                result = media.arr_poster('sonarr', {'images': [{'coverType': 'poster', 'remoteUrl': TVDB}]})
                if size == 1_000_000:
                    self.assertEqual(base64.b64decode(result['poster']), body)
                    self.assertEqual(result['poster_mime'], 'image/png')
                else:
                    self.assertEqual(result, {'poster': '', 'poster_mime': ''})
                self.assertEqual(open_url.call_args.kwargs, {'timeout': 6})

    def test_redirect_blocking_is_used_for_artwork(self):
        self.assertTrue(any(isinstance(h, media.NoRedirect) for h in media.OPENER.handlers))
        with self.assertRaises(ValueError):
            media.NoRedirect().redirect_request(None, None, 302, 'redirect', {}, TVDB)


if __name__ == '__main__':
    unittest.main()
