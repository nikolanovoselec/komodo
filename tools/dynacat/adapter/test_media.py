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
    def test_media_routes_fixed(self):
        with self.assertRaises(KeyError):media.current('http://evil')
if __name__=='__main__':unittest.main()
