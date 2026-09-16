"""Read-only media projections. Fixed origins, bounded reads, no browser credentials."""
import base64
import concurrent.futures
import json
import math
import os
import re
import threading
import time
import urllib.request
from urllib.parse import urlencode, quote
from functools import lru_cache
from media_traffic import TrafficHistory
from media_geo import GeoLocator

MEDIA_GEO = GeoLocator(os.environ.get('DYNACAT_GEO_DB', '/geoip/dbip-city-lite.mmdb'))

PLEX = 'http://192.168.2.205:32400'
ARR = {'sonarr': 'http://192.168.2.38:8988', 'radarr': 'http://192.168.2.38:8309'}
SERVER_ID = '680f79cd6a6313ac1f9f2ab3'
MEDIA_TRAFFIC = TrafficHistory(storage_path=os.environ.get('MEDIA_HISTORY_PATH'))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirect blocked')

OPENER = urllib.request.build_opener(NoRedirect)

def read(url, headers=None, binary=False, limit=6_000_000):
    with OPENER.open(urllib.request.Request(url, headers=headers or {}), timeout=6) as r:
        body = r.read(limit + 1)
        if len(body) > limit:
            raise ValueError('Response too large')
        return body if binary else json.loads(body)

def plex(path):
    token = os.environ.get('DYNACAT_PLEX_TOKEN')
    if not token:
        raise ValueError('Plex credential missing')
    return read(PLEX + path, {'X-Plex-Token': token, 'Accept': 'application/json'})['MediaContainer']

def arr(source, path):
    key = os.environ.get(source.upper() + '_API_KEY')
    if not key:
        raise ValueError('Arr credential missing')
    return read(ARR[source] + '/api/v3/' + path, {'X-Api-Key': key})

def imdb(value):
    return 'https://www.imdb.com/title/' + value + '/' if re.fullmatch(r'tt\d{7,10}', str(value or '')) else ''

def metadata(item):
    ids = [str(g.get('id', '')).removeprefix('imdb://') for g in item.get('Guid', [])]
    return dict(title=item.get('grandparentTitle') or item.get('title', 'Untitled'),
                subtitle=item.get('title', '') if item.get('grandparentTitle') else str(item.get('year') or ''),
                year=item.get('year'), type=item.get('type', 'video'),
                imdb=next((imdb(i) for i in ids if imdb(i)), ''),
                added_at=item.get('addedAt'), duration_ms=item.get('duration'))

def plex_item_url(item, machine):
    # Plex Web/Tautulli's details route. Never session, parent or player IDs.
    key = str(item.get('ratingKey', ''))
    if not re.fullmatch(r'[0-9a-f]{40}', str(machine)) or not re.fullmatch(r'[0-9]+', key):
        return ''
    return 'https://app.plex.tv/desktop/#!/server/' + machine + '/details?' + urlencode({'key':'/library/metadata/' + key}, quote_via=quote)

def plex_machine():
    try:
        return plex('/identity').get('machineIdentifier', '')
    except Exception:
        return ''  # Preserve playback/library telemetry when identity is unavailable.

def sessions():
    data = plex('/status/sessions')
    machine = plex_machine() if data.get('Metadata') else ''
    rows = []
    for item in data.get('Metadata', []):
        row = metadata(item)
        row['plex_url'] = plex_item_url(item, machine)
        row['poster'] = session_poster(item.get('grandparentThumb') or item.get('thumb', ''))
        player = item.get('Player', {})
        session = item.get('Session', {})
        transcode = item.get('TranscodeSession', {})
        media = next((m for m in item.get('Media', []) if m.get('selected')), (item.get('Media') or [{}])[0])
        decision = transcode.get('videoDecision') or transcode.get('audioDecision')
        row.update(user=item.get('User', {}).get('title', 'Viewer'), player=player.get('title', 'Player'),
                   state=player.get('state', 'unknown'), mode='Transcode' if transcode else 'Direct play',
                   decision=decision or 'direct play', resolution=media.get('videoResolution', '—'),
                   progress=min(100, max(0, 100 * item.get('viewOffset', 0) / item['duration'])) if item.get('duration') else None,
                   bandwidth_kbps=session.get('bandwidth'), location=session.get('location', 'unknown'))
        geo = MEDIA_GEO.locate(player.get('address'), player.get('relayed', False))
        row.update(geo_label=geo['label'], geo_status=geo['status'])
        if transcode:
            row['mode'] = 'Transcode' if 'transcode' in (transcode.get('videoDecision'), transcode.get('audioDecision')) else 'Direct stream'
        rows.append(row)
    bw = [r['bandwidth_kbps'] for r in rows if isinstance(r['bandwidth_kbps'], (int, float))]
    return dict(streams=rows, count=len(rows), transcoding=sum(r['mode']=='Transcode' for r in rows),
                direct=sum(r['mode']=='Direct play' for r in rows), has_bandwidth=bool(bw) or not rows,
                bandwidth_coverage=len(bw), bandwidth_mbps=round(sum(bw)/1000, 2) if bw or not rows else None)

def poster(item):
    # Only Plex-generated numeric metadata thumbnail paths; never an input URL.
    path = item.get('grandparentThumb') or item.get('thumb', '')
    if not re.fullmatch(r'/library/metadata/\d+/thumb/\d+', path):
        return ''
    try:
        url = PLEX + '/photo/:/transcode?' + urlencode({'width':200, 'height':300, 'minSize':1, 'upscale':0, 'url':path})
        body = read(url, {'X-Plex-Token': os.environ['DYNACAT_PLEX_TOKEN'], 'Accept':'image/jpeg'}, binary=True, limit=120000)
        return base64.b64encode(body).decode() if body.startswith(b'\xff\xd8') else ''
    except Exception:
        return ''

@lru_cache(maxsize=32)
def session_poster(path):
    # Plex paths carry the artwork version; avoid refetching every 5s sample.
    return poster({'thumb':path})

def library():
    sections = plex('/library/sections').get('Directory', [])
    machine = plex_machine()
    totals, items = [], []
    for section in sections:
        key = str(section.get('key', ''))
        if not key.isdigit(): continue
        count = plex('/library/sections/' + key + '/all?X-Plex-Container-Start=0&X-Plex-Container-Size=0')
        totals.append(dict(title=section.get('title'), type=section.get('type'), total=count.get('totalSize', count.get('size'))))
        if section.get('type') not in ('movie', 'show'): continue
        kind = '4' if section.get('type') == 'show' else '1'
        recent = plex('/library/sections/' + key + '/all?type=' + kind + '&sort=addedAt:desc&includeGuids=1&X-Plex-Container-Start=0&X-Plex-Container-Size=16')
        for item in recent.get('Metadata', []):
            row = metadata(item); row['url'] = plex_item_url(item, machine); row['library'] = section.get('title'); row['_item'] = item; items.append(row)
    items.sort(key=lambda x:x.get('added_at') or 0, reverse=True)
    items = items[:16]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        images = list(pool.map(lambda x:poster(x['_item']), items))
    for row, image in zip(items, images): row.pop('_item'); row['poster'] = image
    return dict(libraries=totals, recent=items)

_ARR_POSTER_CACHE = {}
_ARR_POSTER_LOCK = threading.Lock()


def _arr_poster_image(url, headers=None):
    with _ARR_POSTER_LOCK:
        now = time.monotonic()
        cached = _ARR_POSTER_CACHE.get(url)
        if cached and now - cached[0] < 300:
            return dict(cached[1])
    body = read(url, headers, binary=True, limit=1_000_000) if headers else read(url, binary=True, limit=1_000_000)
    mime = ('image/jpeg' if body.startswith(b'\xff\xd8\xff') else
            'image/png' if body.startswith(b'\x89PNG\r\n\x1a\n') else '')
    result = dict(poster=base64.b64encode(body).decode() if mime else '', poster_mime=mime)
    with _ARR_POSTER_LOCK:
        _ARR_POSTER_CACHE.pop(url, None)
        _ARR_POSTER_CACHE[url] = (time.monotonic(), result)
        while len(_ARR_POSTER_CACHE) > 128:
            _ARR_POSTER_CACHE.pop(next(iter(_ARR_POSTER_CACHE)))
    return dict(result)


def arr_poster(source, entity):
    """Inline artwork only; upstream credentials never enter the projection."""
    try:
        if source == 'radarr':
            key = entity.get('id')
            if type(key) is not int or key <= 0:
                return dict(poster='', poster_mime='')
            return _arr_poster_image(ARR[source] + '/MediaCover/' + str(key) + '/poster-250.jpg',
                                     {'X-Api-Key': os.environ['RADARR_API_KEY']})
        elif source == 'sonarr':
            url = next((i.get('remoteUrl', '') for i in entity.get('images', [])
                        if i.get('coverType') == 'poster'), '')
            if not isinstance(url, str) or not re.fullmatch(
                    r'https://artworks\.thetvdb\.com/banners/[A-Za-z0-9/_\-]+(?:\.[A-Za-z0-9]+)?', url):
                return dict(poster='', poster_mime='')
            return _arr_poster_image(url)
        else:
            return dict(poster='', poster_mime='')

    except Exception:
        pass
    return dict(poster='', poster_mime='')


def arr_data(source):
    # AppRoutes uses the API's titleSlug, not a derived title or the library ID.
    ui = {'sonarr': 'https://sonarr.graymatter.ch/series/', 'radarr': 'https://radarr.graymatter.ch/movie/'}[source]
    def entity_url(entity):
        slug = entity.get('titleSlug')
        return ui + slug if isinstance(slug, str) and re.fullmatch(r'[A-Za-z0-9_-]+', slug) else ''
    history = arr(source, 'history?page=1&pageSize=12&sortKey=date&sortDirection=descending&eventType=3&includeSeries=true&includeEpisode=true&includeMovie=true')
    queue = arr(source, 'queue?page=1&pageSize=30&includeUnknownSeriesItems=false&includeUnknownMovieItems=false&includeSeries=true&includeEpisode=true&includeMovie=true')
    recent, downloads = [], []
    for item in history.get('records', []):
        entity = item.get('series') or item.get('movie') or {}
        episode = item.get('episode') or {}
        recent.append(dict(title=entity.get('title') or 'Imported media', imdb=imdb(entity.get('imdbId')), url=entity_url(entity),
                           subtitle=episode.get('title') or str(entity.get('year') or ''),
                           date=item.get('date'), quality=item.get('quality', {}).get('quality', {}).get('name', 'Unknown'),
                           source=source.title(), **arr_poster(source, entity)))
    for item in queue.get('records', []):
        entity = item.get('series') or item.get('movie') or {}
        size, left = item.get('size'), item.get('sizeleft')
        downloads.append(dict(title=entity.get('title') or item.get('title', 'Download'), imdb=imdb(entity.get('imdbId')), url=entity_url(entity),
                              status=item.get('status', 'unknown'), tracked=item.get('trackedDownloadStatus', ''),
                              progress=round(max(0,min(100,100*(size-left)/size)),1) if size and left is not None else None,
                              remaining_gb=round(left/1e9,2) if left is not None else None,
                              eta=item.get('timeleft') or '—', source=source.title(), **arr_poster(source, entity)))
    return dict(recent=recent, queue=downloads, total=queue.get('totalRecords'), truncated=queue.get('totalRecords',0)>len(downloads))

def import_gallery():
    """Actual Arr imports, explicitly not a substitute for Plex library membership."""
    items=[]
    for source in ('radarr','sonarr'):
        rows=arr(source,'history?page=1&pageSize=30&sortKey=date&sortDirection=descending&eventType=3&includeSeries=true&includeEpisode=true&includeMovie=true')['records']
        seen=set()
        for item in rows:
            entity=item.get('movie') or item.get('series') or {}
            key=entity.get('id')
            if not isinstance(key,int) or key in seen:continue
            seen.add(key)
            from datetime import datetime
            added=int(datetime.fromisoformat(item['date'].replace('Z','+00:00')).timestamp())
            slug=entity.get('titleSlug')
            ui={'sonarr':'https://sonarr.graymatter.ch/series/','radarr':'https://radarr.graymatter.ch/movie/'}[source]
            url=ui+slug if isinstance(slug,str) and re.fullmatch(r'[A-Za-z0-9_-]+',slug) else ''
            row=dict(title=entity.get('title','Imported media'), subtitle=str(entity.get('year') or ''), url=url,
                     imdb=imdb(entity.get('imdbId')), type='movie' if source=='radarr' else 'show',
                     library=source.title()+' import', added_at=added, poster='')
            try:
                if source=='radarr':
                    image=read(ARR[source]+'/MediaCover/'+str(key)+'/poster-250.jpg',{'X-Api-Key':os.environ['RADARR_API_KEY']},binary=True,limit=180000)
                else:
                    from urllib.parse import urlsplit
                    url=next((i.get('remoteUrl','') for i in entity.get('images',[]) if i.get('coverType')=='poster'),'')
                    parsed=urlsplit(url)
                    if parsed.scheme!='https' or parsed.netloc!='artworks.thetvdb.com' or not re.fullmatch(r'/banners/[A-Za-z0-9/_\.\-]+',parsed.path) or parsed.query:
                        raise ValueError('Image origin/path not allowlisted')
                    image=read(url,binary=True,limit=180000)
                if image.startswith(b'\xff\xd8'):row['poster']=base64.b64encode(image).decode()
            except Exception:pass
            items.append(row)
            if len(seen)>=8:break
    items.sort(key=lambda i:i['added_at'],reverse=True)
    return dict(recent=items)


def qbittorrent():
    # Existing LAN access policy permits these fixed read-only API routes.
    # Never logs in, changes settings, or submits torrent/control operations.
    base='http://192.168.2.38:8080/api/v2/'
    # Existing endpoint-directory URL; deployed VueTorrent defines /torrent/:hash/:tab?.
    ui='https://qbittorrent.graymatter.ch/#/'
    transfer=read(base+'transfer/info')
    rows=read(base+'torrents/info?filter=downloading&limit=12&sort=added_on&reverse=true')
    return dict(url=ui, download_mbps=round(transfer['dl_info_speed']*8/1e6,2),
                upload_mbps=round(transfer['up_info_speed']*8/1e6,2),
                state=transfer.get('connection_status','unknown'),
                downloads=[dict(title=r.get('name','Download'),state=r.get('state','unknown'),
                                url=ui+'torrent/'+r['hash'] if isinstance(r.get('hash'),str) and re.fullmatch(r'[0-9a-f]{40}',r['hash']) else ui,
                                progress=round(max(0,min(100,r.get('progress',0)*100)),1),
                                remaining_gb=round(r.get('amount_left',0)/1e9,2)) for r in rows],
                bounded=len(rows)>=12)


def resources():
    import adapter
    data = adapter.api('ListAllDockerContainers', {'limit':0})
    stacks = adapter.api('ListStacks', {'limit':0})
    tags = adapter.api('ListTags', {})
    disabled_tags = {t['_id']['$oid'] for t in tags if t.get('name','').lower()=='disabled'}
    disabled_names = {s['name'] for s in stacks if s.get('info',{}).get('server_id')==SERVER_ID and disabled_tags.intersection(s.get('tags',[]))}
    rows = []
    for name in ('plex', 'emby', 'jellyfin'):
        entry = next((c for c in data if c.get('server_id')==SERVER_ID and c.get('name')=='media_servers_'+name), None)
        stats = (entry or {}).get('stats') or {}
        rows.append(dict(name=name.title(), state=(entry or {}).get('state', 'unavailable'), disabled='media_servers_'+name in disabled_names,
                         status=(entry or {}).get('status', 'Container not returned'),
                         cpu=adapter.number(stats.get('cpu_perc')), has_cpu=adapter.number(stats.get('cpu_perc')) is not None,
                         ram=stats.get('mem_usage', 'Unavailable').split('/')[0].strip(),
                         url={'plex':'https://plex.novoselec.ch', 'emby':'https://emby.novoselec.ch', 'jellyfin':'https://jellyfin.novoselec.ch'}[name],
                         container_url=adapter.komodo_url(SERVER_ID, 'media_servers_'+name),
                         bandwidth='Unavailable · host-network counter', source='Komodo / Docker'))
    hosts = adapter.api('ListServers', {'limit':0})
    host = next((h for h in hosts if h.get('id')==SERVER_ID and h.get('name')=='media_servers' and h.get('info',{}).get('state')=='Ok'), {})
    host_stats=host.get('info',{}).get('stats') or {}
    traffic = MEDIA_TRAFFIC.observe(host_stats)
    return dict(servers=rows,traffic=traffic)

class Source:
    """Demand-driven singleflight. Failures invalidate old data; no upstream lock."""
    def __init__(self, loader, ttl, maximum, label):
        self.loader, self.ttl, self.maximum, self.label = loader, ttl, maximum, label
        self.lock=threading.Lock(); self.at=None; self.started=None; self.data=None; self.busy=False; self.failed=False
    def refresh(self, start):
        try:
            data=self.loader(); json.dumps(data); failed=False
        except Exception:
            data=None; failed=True
        with self.lock:
            self.data=data; self.failed=failed; self.started=start; self.at=time.monotonic(); self.busy=False
    def snapshot(self):
        with self.lock:
            now=time.monotonic()
            if not self.busy and (self.at is None or now-self.at>=self.ttl):
                self.busy=True; threading.Thread(target=self.refresh,args=(now,),daemon=True).start()
            age=None if self.started is None else now-self.started
            state='unavailable' if self.failed else 'starting' if self.data is None else 'expired' if age>self.maximum else 'ready'
            return dict(data=self.data if state=='ready' else {}, state=state, age=round(age or 0),
                        error='' if state=='ready' else self.label+' '+state+' · verify source access', cadence=self.ttl)

SOURCES = {'sessions':Source(sessions,5,30,'Plex playback'), 'library':Source(library,300,660,'Plex library'),
           'resources':Source(resources,5,30,'Komodo media resources'),
           'qbittorrent':Source(qbittorrent,5,30,'qBittorrent'),
           'imports':Source(import_gallery,300,660,'Import artwork'),
           'sonarr':Source(lambda:arr_data('sonarr'),30,90,'Sonarr'), 'radarr':Source(lambda:arr_data('radarr'),30,90,'Radarr')}

def current(kind):
    names={'current':('sessions','resources','qbittorrent'), 'library':('library','imports'), 'arr':('sonarr','radarr')}[kind]
    result = {name:SOURCES[name].snapshot() for name in names}
    if kind == 'current':
        resource = result['resources']
        data = resource.get('data') or {}
        if isinstance(data.get('traffic'), dict):
            # Source snapshots share cached data. Only copy the response projection;
            # age the source timestamp, not its already-included collection age.
            traffic = dict(data['traffic'])
            ts, now = traffic.get('sample_ts'), time.time()
            age = now - ts if type(ts) in (int, float) and math.isfinite(ts) and 0 < ts <= now else None
            traffic['age_seconds'] = age
            traffic['has_age'] = age is not None
            if age is None or age >= MEDIA_TRAFFIC.stale_seconds:
                traffic.update(state='unavailable' if age is None else 'stale',
                               available=False, rx_mbps=None, tx_mbps=None)
            result['resources'] = dict(resource, data=dict(data, traffic=traffic))
    return result
