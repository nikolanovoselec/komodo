import json
import threading
import time
import unittest
from unittest.mock import patch
import media

class MediaTests(unittest.TestCase):
    def test_imdb_validated(self):
        self.assertEqual(media.imdb('tt1234567'),'https://www.imdb.com/title/tt1234567/')
        for bad in ('tt1','https://evil/','tt1234567?token=secret',None): self.assertEqual(media.imdb(bad),'')
    def test_missing_credential_fails_closed(self):
        with patch.dict(media.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):media.plex('/status/sessions')
    def test_session_zero_is_verified_empty(self):
        with patch.object(media,'plex',return_value={'Metadata':[]}):
            self.assertEqual(media.sessions()['count'],0)
            self.assertEqual(media.sessions()['bandwidth_mbps'],0)
    def test_playback_projection(self):
        # Synthetic unit fixture, never served in staging/production.
        row={'title':'Fixture','duration':100000,'viewOffset':25000,'Player':{'state':'playing'},'Session':{'bandwidth':12000},'TranscodeSession':{'videoDecision':'transcode'},'User':{'title':'Viewer'},'secret':'must-not-leak'}
        with patch.object(media,'plex',return_value={'Metadata':[row]}):
            d=media.sessions();self.assertEqual(d['transcoding'],1);self.assertEqual(d['bandwidth_mbps'],12)
            self.assertEqual(d['streams'][0]['progress'],25);self.assertNotIn('must-not-leak',json.dumps(d))
    def test_session_links_exact_episode_not_parent_or_session(self):
        machine = '89c59dcd4e98f6e113cb25eab9ea6e591d9b67ee'
        item = {'title':'Episode 8','type':'episode','ratingKey':'147721',
                'key':'/library/metadata/147721','parentRatingKey':'147720',
                'sessionKey':'private-session','User':{'id':'private-user'}}
        def response(path):
            return {'machineIdentifier':machine} if path == '/identity' else {'Metadata':[item]}
        with patch.object(media,'plex',side_effect=response):
            row = media.sessions()['streams'][0]
        self.assertEqual(row.get('plex_url'), 'https://app.plex.tv/desktop/#!/server/' + machine + '/details?key=%2Flibrary%2Fmetadata%2F147721')
        self.assertNotIn('private-',json.dumps(row))
    def test_plex_url_rejects_untrusted_identifiers(self):
        machine='89c59dcd4e98f6e113cb25eab9ea6e591d9b67ee'
        for key in ('147721?X-Plex-Token=secret','../1','١٢٣','',None):
            self.assertEqual(media.plex_item_url({'ratingKey':key},machine),'')
        for value in ('https://evil/','a'*40+'?secret',None):
            self.assertEqual(media.plex_item_url({'ratingKey':'147721'},value),'')
    def test_identity_failure_retains_playback_without_guessed_link(self):
        def read(path):
            if path=='/identity':raise ValueError('secret')
            return {'Metadata':[{'title':'Fixture','ratingKey':'147721'}]}
        with patch.object(media,'plex',side_effect=read):
            result=media.sessions()
        self.assertEqual(result['count'],1)
        self.assertEqual(result['streams'][0]['plex_url'],'')
        self.assertNotIn('secret',json.dumps(result))
    def test_library_items_exact_links_and_imdb_remains_secondary(self):
        machine='89c59dcd4e98f6e113cb25eab9ea6e591d9b67ee'
        def read(path):
            if path=='/identity':return {'machineIdentifier':machine}
            if path=='/library/sections':return {'Directory':[{'key':'2','type':'show'}]}
            if 'Container-Size=0' in path:return {'totalSize':1}
            return {'Metadata':[{'ratingKey':'147721','title':'Episode 8','type':'episode','Guid':[{'id':'imdb://tt1234567'}]}]}
        with patch.object(media,'plex',side_effect=read),patch.object(media,'poster',return_value=''):
            result=media.library()['recent'][0]
        self.assertTrue(result['url'].endswith('/details?key=%2Flibrary%2Fmetadata%2F147721'))
        self.assertEqual(result['imdb'],'https://www.imdb.com/title/tt1234567/')
    def test_session_poster_cached_and_proxy_only(self):
        media.session_poster.cache_clear()
        with patch.object(media,'poster',return_value='base64') as load:
            self.assertEqual(media.session_poster('/library/metadata/1/thumb/123'),'base64')
            self.assertEqual(media.session_poster('/library/metadata/1/thumb/123'),'base64')
            self.assertEqual(load.call_count,1)
        media.session_poster.cache_clear()
    def test_missing_bandwidth_not_zero(self):
        with patch.object(media,'plex',return_value={'Metadata':[{'title':'Fixture'}]}):
            self.assertIsNone(media.sessions()['bandwidth_mbps'])
    def test_poster_rejects_arbitrary_path(self):
        with patch.object(media,'read') as read:
            self.assertEqual(media.poster({'thumb':'http://evil/secret'}),'');read.assert_not_called()
    def test_poster_rejects_non_image(self):
        with patch.dict(media.os.environ, {'DYNACAT_PLEX_TOKEN':'test'}),patch.object(media,'read',return_value=b'<html>'):
            self.assertEqual(media.poster({'thumb':'/library/metadata/1/thumb/123'}),'')
    def test_redirects_blocked(self):
        with self.assertRaises(ValueError):media.NoRedirect().redirect_request(None,None,None,None,None,None)
    def test_source_nonblocking_singleflight(self):
        started=threading.Event();release=threading.Event();calls=[]
        def load():calls.append(1);started.set();release.wait(2);return {'value':1}
        source=media.Source(load,5,30,'Test');at=time.monotonic()
        self.assertEqual(source.snapshot()['state'],'starting');started.wait(1)
        for _ in range(20):source.snapshot()
        self.assertLess(time.monotonic()-at,.5);self.assertEqual(len(calls),1)
        release.set()
    def test_source_failure_clears_old_snapshot(self):
        source=media.Source(lambda: {'old':True},5,30,'Test');source.refresh(time.monotonic())
        self.assertEqual(source.snapshot()['state'],'ready')
        def fail():raise ValueError('secret')
        source.loader=fail;source.refresh(time.monotonic())
        d=source.snapshot();self.assertEqual(d['data'],{});self.assertEqual(d['state'],'unavailable');self.assertNotIn('secret',json.dumps(d))
    def test_source_expiry(self):
        source=media.Source(lambda: {},100,30,'Test');source.refresh(time.monotonic()-40)
        self.assertEqual(source.snapshot()['state'],'expired')
    def test_resource_missing_stats_is_not_zero(self):
        import adapter
        with patch.object(adapter,'api',return_value=[{'server_id':media.SERVER_ID,'name':'media_servers_jellyfin','state':'exited'}]):
            rows=media.resources()['servers'];self.assertFalse(rows[2]['has_cpu']);self.assertIsNone(rows[2]['cpu'])
    def test_library_requests_episode_items_not_seasons(self):
        calls=[]
        def response(path):
            calls.append(path)
            if path=='/library/sections':return {'Directory':[{'key':'2','title':'Shows','type':'show'}]}
            if 'Container-Size=0' in path:return {'totalSize':4}
            self.assertIn('type=4',path);self.assertIn('sort=addedAt:desc',path);self.assertIn('Container-Size=16',path)
            return {'Metadata':[{'title':'New episode','grandparentTitle':'Existing show','type':'episode','addedAt':100,'Guid':[{'id':'imdb://tt1234567'}]}]}
        with patch.object(media,'plex',side_effect=response),patch.object(media,'poster',return_value=''):
            d=media.library();self.assertEqual(d['recent'][0]['title'],'Existing show');self.assertEqual(d['recent'][0]['subtitle'],'New episode')
    def test_arr_import_and_queue_projection(self):
        calls=[]
        def response(source,path):
            calls.append(path)
            if path.startswith('history'):
                self.assertIn('eventType=3',path)
                return {'records':[{'movie':{'title':'Fixture','imdbId':'tt1234567'},'data':{'secret':'hidden'}}]}
            return {'totalRecords':31,'records':[{'title':'Fixture','size':100,'sizeleft':25,'status':'downloading'}]}
        with patch.object(media,'arr',side_effect=response):
            d=media.arr_data('radarr');self.assertTrue(d['truncated']);self.assertEqual(d['queue'][0]['progress'],75);self.assertNotIn('secret',json.dumps(d))
    def test_partial_bandwidth_keeps_reported_value_and_coverage(self):
        with patch.object(media,'plex',return_value={'Metadata':[{'Session':{'bandwidth':2384}},{}]}):
            d=media.sessions();self.assertEqual(d['bandwidth_mbps'],2.38);self.assertEqual(d['bandwidth_coverage'],1);self.assertEqual(d['count'],2)
    def test_qbittorrent_readonly_rates(self):
        def read(url):
            self.assertTrue(url.startswith('http://192.168.2.38:8080/api/v2/'))
            if url.endswith('transfer/info'):return {'dl_info_speed':125000,'up_info_speed':250000,'connection_status':'connected'}
            self.assertIn('filter=downloading&limit=12',url);return []
        with patch.object(media,'read',side_effect=read):
            d=media.qbittorrent();self.assertEqual(d['download_mbps'],1);self.assertEqual(d['upload_mbps'],2);self.assertEqual(d['downloads'],[])
    def test_media_routes_fixed(self):
        with self.assertRaises(KeyError):media.current('http://evil')
if __name__=='__main__':unittest.main()
