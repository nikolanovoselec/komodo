"""Offline destination validation; importing QA must never start a browser."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('qa_navigation', Path(__file__).resolve().parents[1] / 'qa_media_navigation.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class PopupLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_popup_load_timeout_and_errors_are_not_swallowed(self):
        from unittest.mock import AsyncMock, Mock
        popup = Mock(url='https://plex.novoselec.ch',
                     wait_for_load_state=AsyncMock(side_effect=TimeoutError('load failed')))
        with self.assertRaises(TimeoutError):
            await qa.verify_popup(popup, popup.url, [])
        popup.wait_for_load_state = AsyncMock()
        popup.wait_for_timeout = AsyncMock()
        with self.assertRaises(AssertionError):
            await qa.verify_popup(popup, popup.url, ['popup load error'])


class NavigationQATests(unittest.TestCase):
    def test_exact_destination_and_known_auth_redirects(self):
        plex = 'https://app.plex.tv/desktop/#!/server/' + 'a'*40 + '/details?key=%2Flibrary%2Fmetadata%2F1'
        arr = 'https://sonarr.graymatter.ch/series/1883'
        self.assertEqual(qa.navigation_destination(plex, plex), (plex, False))
        for expected, actual, safe in [
            (plex, 'https://app.plex.tv/auth/#?clientID=secret', 'https://app.plex.tv/auth/'),
            ('https://plex.novoselec.ch', 'https://app.plex.tv/auth/?state=secret#token', 'https://app.plex.tv/auth/'),
            (arr, 'https://authentik.graymatter.ch/if/flow/default-authentication-flow/?next=secret#state', 'https://authentik.graymatter.ch/if/flow/default-authentication-flow/')]:
            self.assertEqual(qa.navigation_destination(expected, actual), (safe, True))

    def test_wrong_destinations_fail_without_exposing_redirect_state(self):
        expected = 'https://sonarr.graymatter.ch/series/1883'
        for actual in ['about:blank', 'chrome-error://chromewebdata/',
                       'https://sonarr.graymatter.ch/series/wrong',
                       'https://app.plex.tv/auth/',
                       'https://authentik.graymatter.ch/if/flow/not-authentication/?state=secret',
                       'https://authentik.graymatter.ch.evil/if/flow/default-authentication-flow/',
                       'https://user@authentik.graymatter.ch/if/flow/default-authentication-flow/',
                       'http://authentik.graymatter.ch/if/flow/default-authentication-flow/',
                       'https://authentik.graymatter.ch/if/flow/default-authentication-flow/extra?secret']:
            with self.subTest(actual=actual), self.assertRaises(AssertionError) as error:
                qa.navigation_destination(expected, actual)
            self.assertNotIn('secret', str(error.exception))
        with self.assertRaises(AssertionError):
            qa.navigation_destination('https://evil.example/', 'https://authentik.graymatter.ch/if/flow/default-authentication-flow/')
