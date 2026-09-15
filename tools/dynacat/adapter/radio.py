"""Read-only section 21 radio. Run: python3 /app/radio.py (port 8091)."""
import re
import json
import os
import time
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import media

MAX_SIZE = 2**31
ID = re.compile(r'[0-9]{1,20}')
PART = re.compile(r'/library/parts/[0-9]+/[0-9]+/file\.([a-z0-9]{1,5})')
FORMATS = {
    ('mp3', 'mp3'): ('mp3', 'audio/mpeg'),
    ('aac', 'aac'): ('aac', 'audio/aac'),
    ('aac', 'mp4'): ('m4a', 'audio/mp4'),
    ('aac', 'm4a'): ('m4a', 'audio/mp4'),
    ('flac', 'flac'): ('flac', 'audio/flac'),
    ('opus', 'ogg'): ('ogg', 'audio/ogg'),
    ('opus', 'opus'): ('opus', 'audio/ogg'),
    ('vorbis', 'ogg'): ('ogg', 'audio/ogg'),
    ('pcm', 'wav'): ('wav', 'audio/wav'),
    ('pcm_s16le', 'wav'): ('wav', 'audio/wav'),
    ('pcm_s24le', 'wav'): ('wav', 'audio/wav'),
}


def source(item):
    if not isinstance(item, dict) or item.get('type') != 'track' or str(item.get('librarySectionID')) != '21' or not ID.fullmatch(str(item.get('ratingKey', ''))):
        return None
    versions = item.get('Media')
    if not isinstance(versions, list):
        return None
    for version in versions[:8]:
        if not isinstance(version, dict) or not isinstance(version.get('audioCodec'), str) or not isinstance(version.get('container'), str):
            continue
        fmt = FORMATS.get((version.get('audioCodec'), version.get('container')))
        parts = version.get('Part', [])
        if not fmt or not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
            continue
        part = parts[0]
        match = PART.fullmatch(str(part.get('key', '')))
        size = part.get('size')
        if match and match[1] == fmt[0] and type(size) is int and 0 < size <= MAX_SIZE:
            return part['key'], size, fmt[1], version['audioCodec']
    return None


def queue():
    container = media.plex('/library/sections/21/all?type=10&sort=random&X-Plex-Container-Start=0&X-Plex-Container-Size=64')
    if 'librarySectionID' in container and str(container['librarySectionID']) != '21':
        return {'tracks': []}
    rows = container.get('Metadata', [])
    tracks = []
    for item in rows[:64]:
        # Section listings may scope tracks only on their MediaContainer.
        if isinstance(item, dict) and 'librarySectionID' not in item and str(container.get('librarySectionID')) == '21':
            item = dict(item, librarySectionID='21')
        selected = source(item)
        if not selected or any(row['id'] == str(item['ratingKey']) for row in tracks):
            continue
        if len(tracks) >= 16:
            break
        image = media.session_poster(item.get('parentThumb', ''))
        tracks.append(dict(id=str(item['ratingKey']), title=item.get('title', ''),
                           artist=item.get('grandparentTitle', ''), album=item.get('parentTitle', ''),
                           duration_ms=item.get('duration'), codec=selected[3],
                           poster='data:image/jpeg;base64,' + image if image else '',
                           stream='/radio/stream/' + str(item['ratingKey'])))
    return {'tracks': tracks}


UPSTREAM_TIMEOUT = 8
CLIENT_TIMEOUT = 10
STREAM_DEADLINE = 300
MAX_WORKERS = 8


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirect blocked')


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def byte_range(value, size):
    if value is None:
        return 0, size - 1
    match = re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})', value)
    if not match or not any(match.groups()):
        raise ValueError('Invalid range')
    first, last = match.groups()
    if not first:
        length = int(last)
        if length == 0:
            raise ValueError('Invalid range')
        return max(0, size - length), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError('Invalid range')
    return start, end


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 closes each connection: no unbounded keepalive work per client.
    server_version = 'Radio'
    sys_version = ''

    def setup(self):
        self.request.settimeout(CLIENT_TIMEOUT)
        super().setup()

    def log_message(self, format, *args):
        pass

    def json(self, status, data, extra=None):
        body = json.dumps(data, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        self.json(code, {'error': 'Request rejected'})

    def do_GET(self):
        try:
            if self.path == '/radio/queue' and self.command == 'GET':
                self.json(200, queue())
                return
            match = re.fullmatch(r'/radio/stream/([0-9]{1,20})', self.path)
            if match:
                self.stream(match[1])
            else:
                self.json(404, {'error': 'Not found'})
        except (BrokenPipeError, ConnectionError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.json(502, {'error': 'Radio upstream unavailable'})

    do_HEAD = do_GET

    def do_POST(self):
        self.json(405, {'error': 'Method not allowed'}, {'Allow': 'GET, HEAD'})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

    def stream(self, identifier):
        rows = media.plex('/library/metadata/' + identifier).get('Metadata', [])
        if len(rows) != 1 or str(rows[0].get('ratingKey')) != identifier:
            self.json(404, {'error': 'Track unavailable'})
            return
        selected = source(rows[0])
        if not selected:
            self.json(404, {'error': 'Track unavailable'})
            return
        key, size, mime, _ = selected
        ranges = self.headers.get_all('Range', [])
        value = ranges[0] if ranges else None
        try:
            if len(ranges) > 1:
                raise ValueError('Multiple ranges')
            start, end = byte_range(value, size)
        except ValueError:
            self.json(416, {'error': 'Range not satisfiable'}, {'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
            return
        token = os.environ.get('DYNACAT_PLEX_TOKEN')
        if not token:
            raise ValueError('Missing credential')
        headers = {'X-Plex-Token': token, 'Accept-Encoding': 'identity'}
        if value is not None:
            headers['Range'] = f'bytes={start}-{end}'
        expected = 206 if value is not None else 200
        length = end - start + 1
        content_range = f'bytes {start}-{end}/{size}'
        request = urllib.request.Request(media.PLEX + key, headers=headers, method=self.command)
        with self.server.opener.open(request, timeout=UPSTREAM_TIMEOUT) as response:
            if response.status != expected or response.headers.get('Content-Length') != str(length):
                raise ValueError('Upstream framing mismatch')
            if response.headers.get('Content-Encoding', 'identity') != 'identity' or response.headers.get('Transfer-Encoding'):
                raise ValueError('Encoded upstream body')
            if expected == 206 and response.headers.get('Content-Range') != content_range:
                raise ValueError('Upstream range mismatch')
            self.send_response(expected)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'private, no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if expected == 206:
                self.send_header('Content-Range', content_range)
            self.end_headers()
            if self.command == 'HEAD':
                return
            deadline = time.monotonic() + STREAM_DEADLINE
            # After headers are sent, failures must close, never append JSON to audio.
            try:
                while length and time.monotonic() < deadline:
                    chunk = response.read(min(65536, length))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    length -= len(chunk)
            except Exception:
                pass
            finally:
                self.close_connection = True


class RadioServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, opener):
        self.opener = opener
        self.slots = threading.BoundedSemaphore(MAX_WORKERS)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never log credentials, upstream exceptions, or access paths.


def make_server(address=('0.0.0.0', 8091), *, opener=None):
    return RadioServer(address, OPENER if opener is None else opener)


if __name__ == '__main__':
    with make_server() as server:
        server.serve_forever()
