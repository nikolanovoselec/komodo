import copy
import importlib
import unittest
from unittest.mock import patch


def track():
    return {'type':'track','librarySectionID':'21','ratingKey':'12','title':'Song','grandparentTitle':'Artist','parentTitle':'Album','duration':123000,'parentThumb':'/library/metadata/8/thumb/9','Media':[{'audioCodec':'mp3','container':'mp3','Part':[{'key':'/library/parts/1/2/file.mp3','size':10}]}]}


class RadioTests(unittest.TestCase):
    def test_queue_projects_actual_tracks_and_bounds_lookup(self):
        radio = importlib.import_module('radio')
        with patch.object(radio.media, 'plex', return_value={'Metadata':[track()]}) as plex, patch.object(radio.media,'session_poster',return_value='/9g=') as poster:
            result = radio.queue()
        self.assertEqual(result['tracks'], [{'id':'12','title':'Song','artist':'Artist','album':'Album','duration_ms':123000,'codec':'mp3','poster':'data:image/jpeg;base64,/9g=','stream':'/radio/stream/12'}])
        self.assertIn('/library/sections/21/all?type=10&sort=random',plex.call_args.args[0])
        self.assertIn('X-Plex-Container-Size=64',plex.call_args.args[0])
        poster.assert_called_once_with('/library/metadata/8/thumb/9')

    def test_queue_inherits_section_from_verified_container(self):
        import radio
        row = track()
        del row['librarySectionID']
        original = copy.deepcopy(row)
        for section in ['21', 21]:
            with self.subTest(section=section), patch.object(radio.media, 'plex', return_value={'librarySectionID': section, 'Metadata': [row]}), patch.object(radio.media, 'session_poster', return_value=''):
                self.assertEqual([item['id'] for item in radio.queue()['tracks']], ['12'])
                self.assertEqual(row, original)
                self.assertIsNone(radio.source(row))

    def test_queue_rejects_conflicting_container_scope(self):
        import radio
        for section in ['22', 22, None, '', '021']:
            with self.subTest(section=section), patch.object(radio.media, 'plex', return_value={'librarySectionID': section, 'Metadata': [track()]}), patch.object(radio.media, 'session_poster') as poster:
                self.assertEqual(radio.queue(), {'tracks': []})
                poster.assert_not_called()

    def test_queue_does_not_inherit_unverified_scope(self):
        import radio
        row = track()
        del row['librarySectionID']
        for scope in [{}, {'librarySectionID': '22'}, {'librarySectionID': None}]:
            with self.subTest(scope=scope), patch.object(radio.media, 'plex', return_value={**scope, 'Metadata': [row]}), patch.object(radio.media, 'session_poster') as poster:
                self.assertEqual(radio.queue(), {'tracks': []})
                poster.assert_not_called()

    def test_queue_preserves_explicit_invalid_track_scope(self):
        import radio
        for section in ['22', 22, None, '', '021']:
            row = track()
            row['librarySectionID'] = section
            with self.subTest(section=section), patch.object(radio.media, 'plex', return_value={'librarySectionID': '21', 'Metadata': [row]}), patch.object(radio.media, 'session_poster') as poster:
                self.assertEqual(radio.queue(), {'tracks': []})
                poster.assert_not_called()

    def test_all_supported_formats_and_selected_version(self):
        import radio
        for codec, container, extension in [('mp3','mp3','mp3'),('aac','aac','aac'),('aac','mp4','m4a'),('flac','flac','flac'),('opus','ogg','ogg'),('vorbis','ogg','ogg'),('pcm_s16le','wav','wav')]:
            row = track(); row['Media'][0].update(audioCodec=codec,container=container)
            row['Media'][0]['Part'][0]['key']='/library/parts/1/2/file.'+extension
            self.assertIsNotNone(radio.source(row))
        row=track(); row['Media'].insert(0,{'audioCodec':'alac','container':'mp4','Part':[]})
        with patch.object(radio.media,'plex',return_value={'Metadata':[row]}),patch.object(radio.media,'session_poster',return_value=''):
            self.assertEqual(radio.queue()['tracks'][0]['codec'],'mp3')

    def test_queue_ignores_malformed_media_records(self):
        import radio
        rows=[]
        for value in [None,{},'bad',[None],[{'Part':None}], [{'audioCodec':[], 'container':'mp3'}]]:
            row=track(); row['Media']=value; rows.append(row)
        with patch.object(radio.media,'plex',return_value={'Metadata':rows}),patch.object(radio.media,'session_poster',return_value=''):
            self.assertEqual(radio.queue(),{'tracks':[]})

    def test_queue_rejects_unsafe_or_unsupported_tracks(self):
        import radio
        invalid = []
        for field, value in [('type','movie'),('librarySectionID','22'),('ratingKey','12?token=x')]:
            row = track(); row[field] = value; invalid.append(row)
        for key in ['http://evil/file.mp3','/library/parts/1/2/file.mp3?token=x','/library/parts/1/2/../file.mp3']:
            row = track(); row['Media'][0]['Part'][0]['key'] = key; invalid.append(row)
        for codec, container in [('alac','mp4'),('aac','mkv'),('mp3','mkv')]:
            row = track(); row['Media'][0].update(audioCodec=codec,container=container); invalid.append(row)
        row = track(); row['Media'][0]['Part'][0]['size'] = 2**31 + 1; invalid.append(row)
        with patch.object(radio.media,'plex',return_value={'Metadata':invalid + [track()]*100}), patch.object(radio.media,'session_poster',return_value=''):
            result = radio.queue()
        self.assertEqual(len(result['tracks']),1)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        import radio
        import threading
        import urllib.request
        from http.server import BaseHTTPRequestHandler, HTTPServer
        self.radio = radio
        self.seen = []
        self.mode = 'normal'
        outer = self
        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.seen.append((self.path, self.headers.get('X-Plex-Token'), self.headers.get('Range')))
                if outer.mode == 'redirect':
                    self.send_response(302); self.send_header('Location','http://example.invalid/secret'); self.end_headers(); return
                start, end = (0, 9)
                if self.headers.get('Range'):
                    start, end = map(int, self.headers['Range'][6:].split('-'))
                body = b'0123456789'[start:end+1]
                self.send_response(206 if self.headers.get('Range') else 200)
                self.send_header('Content-Length',str(len(body)))
                if self.headers.get('Range'):
                    self.send_header('Content-Range',f'bytes {start}-{end}/10' if outer.mode != 'bad-range' else 'bytes 0-0/100')
                self.end_headers(); self.wfile.write(body)
            do_HEAD = do_GET
            def log_message(self,*args): pass
        self.upstream = HTTPServer(('127.0.0.1',0),Upstream)
        threading.Thread(target=self.upstream.serve_forever,daemon=True).start()
        actual_opener = urllib.request.build_opener(radio.NoRedirect)
        class LocalOpener:
            def open(inner, req, timeout):
                self.assertEqual(timeout, radio.UPSTREAM_TIMEOUT)
                self.assertTrue(req.full_url.startswith(radio.media.PLEX + '/library/parts/'))
                local = urllib.request.Request('http://127.0.0.1:%d%s' % (self.upstream.server_port,req.selector),headers=dict(req.header_items()),method=req.method)
                return actual_opener.open(local,timeout=timeout)
        self.metadata = track()
        self.patches = [patch.object(radio.media,'plex',side_effect=lambda path: {'Metadata':[self.metadata]}),patch.dict('os.environ',{'DYNACAT_PLEX_TOKEN':'server-secret'})]
        for p in self.patches: p.start()
        self.server = radio.make_server(('127.0.0.1',0),opener=LocalOpener())
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def tearDown(self):
        for server in (self.server,self.upstream): server.shutdown(); server.server_close()
        for p in reversed(self.patches): p.stop()

    def request(self, method='GET',path='/radio/stream/12',headers=None):
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        conn.request(method,path,headers=headers or {})
        response=conn.getresponse(); result=(response.status,dict(response.getheaders()),response.read()); conn.close(); return result

    def test_stream_get_head_and_single_ranges(self):
        for method, value, status, body in [('GET',None,200,b'0123456789'),('HEAD',None,200,b''),('GET','bytes=2-4',206,b'234'),('GET','bytes=8-',206,b'89'),('GET','bytes=-3',206,b'789'),('HEAD','bytes=2-4',206,b'')]:
            with self.subTest(method=method,value=value):
                code, headers, data = self.request(method,headers={'Range':value} if value else {})
                self.assertEqual((code,data),(status,body))
                self.assertEqual(headers['Content-Type'],'audio/mpeg')
                self.assertEqual(headers['Accept-Ranges'],'bytes')
                self.assertNotIn('server-secret',str(headers))
                if value: self.assertIn('Content-Range',headers)
        self.assertTrue(all(row[1] == 'server-secret' for row in self.seen))

    def test_invalid_ranges_do_not_contact_upstream(self):
        for value in ['bytes=10-','bytes=3-2','bytes=-0','bytes=1-2,4-5','items=0-1','bytes=' + '9'*1000 + '-']:
            code,headers,_=self.request(headers={'Range':value})
            self.assertEqual(code,416); self.assertEqual(headers['Content-Range'],'bytes */10')
        self.assertEqual(self.seen,[])

    def test_stream_revalidates_scope_and_hides_errors(self):
        self.metadata['librarySectionID']='22'
        self.assertEqual(self.request()[0],404)
        self.assertEqual(self.seen,[])
        self.metadata=track()
        for mode in ['redirect','bad-range']:
            self.mode=mode
            code,headers,body=self.request(headers={'Range':'bytes=2-4'})
            self.assertEqual(code,502)
            self.assertNotIn(b'server-secret',body)
            self.assertNotIn('Location',headers)

    def test_worker_capacity_and_timeouts_are_bounded(self):
        import socket
        self.assertEqual(self.server.request_queue_size,8)
        self.assertEqual(self.radio.UPSTREAM_TIMEOUT,8)
        self.assertEqual(self.radio.CLIENT_TIMEOUT,10)
        for _ in range(self.radio.MAX_WORKERS):
            self.assertTrue(self.server.slots.acquire(blocking=False))
        try:
            with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=2) as connection:
                self.assertEqual(connection.recv(1),b'')
        finally:
            for _ in range(self.radio.MAX_WORKERS): self.server.slots.release()
        self.assertEqual(self.request()[0],200)

    def test_dispatch_is_radio_only(self):
        for path in ['/api/sessions','/radio/stream/12?url=http://evil','/radio/stream/%31%32','/radio/queue?limit=10000']:
            self.assertEqual(self.request(path=path)[0],404)
        code,headers,body=self.request('POST')
        self.assertEqual(code,405)
        self.assertEqual(headers['Content-Type'],'application/json')


if __name__ == '__main__':
    unittest.main()
