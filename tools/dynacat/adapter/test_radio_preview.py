import http.client
import json
import threading
import unittest
from unittest.mock import Mock, patch

import radio
from test_radio import track


class PreviewTests(unittest.TestCase):
    def setUp(self):
        # Each test starts with an empty process-local preview cache.
        radio._preview_value = None
        radio._preview_expires = 0

    def test_preview_exposes_validated_base64_for_native_image_url_prefix(self):
        for image, expected in [('YWJj', 'YWJj'), ('javascript:bad', ''), ('', '')]:
            radio._preview_value = None
            with self.subTest(image=image), patch.object(radio.media, 'plex', return_value={'Metadata': [track()]}), patch.object(radio.media, 'session_poster', return_value=image):
                self.assertEqual(radio.preview().get('poster_base64'), expected)

    def test_preview_cache_expires_after_300_seconds_but_queue_stays_fresh(self):
        rows = [dict(track(), ratingKey=str(i)) for i in range(1, 65)]
        with patch.object(radio.media, 'plex', return_value={'Metadata': rows}) as plex, \
                patch.object(radio.media, 'session_poster', return_value='') as poster, \
                patch.object(radio.time, 'monotonic', return_value=1000) as clock:
            first = radio.preview()
            clock.return_value = 1299.99
            self.assertEqual(radio.preview(), first)
            self.assertEqual(plex.call_count, 1)
            self.assertEqual(poster.call_count, 1)
            clock.return_value = 1300
            radio.preview()
            self.assertEqual(plex.call_count, 2)
            self.assertEqual(poster.call_count, 2)
            self.assertEqual(len(radio.queue()['tracks']), 16)
            self.assertEqual(len(radio.queue()['tracks']), 16)
            self.assertEqual(plex.call_count, 4)
            self.assertEqual(poster.call_count, 34)

    def test_concurrent_preview_misses_share_one_upstream_fetch(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(6)
        release = threading.Event()
        entered = threading.Event()

        def upstream(_path):
            entered.set()
            self.assertTrue(release.wait(3))
            return {'Metadata': [track()]}

        def request():
            barrier.wait(3)
            return radio.preview()

        with patch.object(radio.media, 'plex', side_effect=upstream) as plex, \
                patch.object(radio.media, 'session_poster', return_value='') as poster:
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [pool.submit(request) for _ in range(6)]
                self.assertTrue(entered.wait(3))
                # Give all simultaneous callers time to reach the blocked fetch.
                threading.Event().wait(0.1)
                release.set()
                results = [future.result(3) for future in futures]
            self.assertTrue(all(result == results[0] for result in results))
            plex.assert_called_once()
            poster.assert_called_once()

    def test_failed_refresh_is_redacted_and_cached_for_30_seconds(self):
        with patch.object(radio.media, 'plex', side_effect=RuntimeError('secret-token https://private/')) as plex, \
                patch.object(radio.media, 'session_poster') as poster, \
                patch.object(radio.time, 'monotonic', return_value=1000) as clock:
            # Catch the old uncaught exception to make the missing contract explicit.
            try:
                first = radio.preview()
            except Exception as error:
                first = str(error)
            self.assertEqual(first, {'track': None, 'error': 'Radio upstream unavailable'})
            clock.return_value = 1029.99
            self.assertEqual(radio.preview(), first)
            self.assertEqual(plex.call_count, 1)
            clock.return_value = 1030
            plex.side_effect = None
            plex.return_value = {'Metadata': [track()]}
            poster.return_value = ''
            recovered = radio.preview()
            self.assertEqual(recovered['track']['id'], '12')
            self.assertEqual(recovered['error'], '')
            self.assertEqual(plex.call_count, 2)
            poster.assert_called_once()

    def test_empty_library_has_honest_short_lived_empty_state(self):
        with patch.object(radio.media, 'plex', return_value={'Metadata': []}) as plex, \
                patch.object(radio.media, 'session_poster') as poster, \
                patch.object(radio.time, 'monotonic', return_value=1000) as clock:
            expected = {'track': None, 'error': 'No playable tracks available'}
            self.assertEqual(radio.preview(), expected)
            clock.return_value = 1029
            self.assertEqual(radio.preview(), expected)
            plex.assert_called_once()
            clock.return_value = 1030
            self.assertEqual(radio.preview(), expected)
            self.assertEqual(plex.call_count, 2)
            poster.assert_not_called()

    def test_http_preview_projects_one_playable_track_without_playback(self):
        invalid = dict(track(), type='movie')
        rows = [invalid] + [dict(track(), ratingKey=str(i)) for i in range(1, 65)]
        opener = Mock()
        with patch.object(radio.media, 'plex', return_value={'Metadata': rows}) as plex, \
                patch.object(radio.media, 'session_poster', return_value='YWJj') as poster, \
                patch.object(radio.Handler, 'stream') as stream:
            with radio.make_server(('127.0.0.1', 0), opener=opener) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    connection = http.client.HTTPConnection(*server.server_address, timeout=3)
                    connection.request('GET', '/radio/preview')
                    response = connection.getresponse()
                    body = json.loads(response.read())
                    connection.close()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader('Content-Type'), 'application/json')
                    self.assertEqual(body, {'track': {
                        'id': '1', 'title': 'Song', 'artist': 'Artist', 'album': 'Album',
                        'duration_ms': 123000, 'codec': 'mp3',
                        'poster': 'data:image/jpeg;base64,YWJj', 'stream': '/radio/stream/1',
                    }, 'error': '', 'poster_base64': 'YWJj'})
                finally:
                    server.shutdown()
                    worker.join(3)
            plex.assert_called_once_with('/library/sections/21/all?type=10&sort=random&X-Plex-Container-Start=0&X-Plex-Container-Size=64')
            poster.assert_called_once_with('/library/metadata/8/thumb/9')
            stream.assert_not_called()
            opener.open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
