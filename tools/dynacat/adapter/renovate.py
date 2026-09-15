"""Public, read-only Renovate PR telemetry for the one allowlisted repository."""
import time
import copy
import threading
import json
import re
import os
import urllib.request

CACHE_SECONDS = 600
_cache = None
_lock = threading.Lock()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _page(page):
    if type(page) is not int or not 1 <= page <= 5:
        raise ValueError('Page outside bounded range')
    # Ignore Link target URLs entirely: construct every request locally.
    url = 'https://api.github.com/repos/nikolanovoselec/komodo/pulls?state=open&per_page=100'
    if page != 1:
        url += f'&page={page}'
    headers = {'Accept': 'application/vnd.github+json',
               'User-Agent': 'dynacat-renovate-summary', 'X-GitHub-Api-Version': '2022-11-28'}
    # This protected service token is never projected, logged or sent to the browser.
    token = os.environ.get('DYNACAT_GITHUB_TOKEN', '')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(url, method='GET', headers=headers)
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError('Unexpected GitHub status')
        data = json.load(response)
        if not isinstance(data, list) or len(data) > 100 or any(not isinstance(r, dict) for r in data):
            raise ValueError('Malformed GitHub pull list')
        more = bool(re.search(r';\s*rel="next"', response.headers.get('Link', '')))
        return data, more


def collect():
    """Share a ten-minute snapshot across callers; return independent copies."""
    global _cache
    with _lock:
        if _cache is None or time.monotonic() >= _cache[0]:
            try:
                result = _collect()
            except Exception:
                # Never turn failed/partial retrieval into a green zero count.
                result = {'error': 'Renovate PRs unavailable; GitHub API, network or response error',
                          'prs': None, 'count': None, 'truncated': False,
                          'fetched_at': int(time.time())}
            _cache = (time.monotonic() + CACHE_SECONDS, result)
        return copy.deepcopy(_cache[1])


def _collect():
    rows = []
    for page in range(1, 6):
        batch, truncated = _page(page)
        rows.extend(batch)
        if not truncated:
            break
    rows = list({row['number']: row for row in rows}.values())
    prs = []
    for row in rows:
        if row.get('state') == 'open' and row.get('user', {}).get('login') == 'renovate[bot]':
            number = row['number']
            if type(number) is not int or number <= 0 or not isinstance(row['title'], str):
                raise ValueError('Malformed pull request')
            prs.append({'number': number, 'title': row['title'],
                        'url': f'https://github.com/nikolanovoselec/komodo/pull/{number}',
                        'updated_at': row.get('updated_at')})
    return {'prs': prs, 'count': len(prs), 'truncated': truncated,
            'fetched_at': int(time.time())}
