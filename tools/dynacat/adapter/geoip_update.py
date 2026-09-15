"""DB-IP Lite maintenance; only the database URL is fetched, never a viewer IP."""
import gzip
import os
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import re
import time
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Database redirect blocked')


OPENER = urllib.request.build_opener(NoRedirect)


def update_database(directory, month, *, fetch=OPENER.open,
                    compressed_limit=100_000_000, expanded_limit=250_000_000):
    import maxminddb
    if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', month):
        raise ValueError('Expected YYYY-MM')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'dbip-city-lite.mmdb'
    try:
        with maxminddb.open_database(str(target)) as reader:
            metadata = reader.metadata()
            if (metadata.database_type == 'DBIP-City-Lite'
                    and datetime.fromtimestamp(metadata.build_epoch, timezone.utc).strftime('%Y-%m') == month):
                return 'current'
    except Exception:
        pass  # Missing/corrupt cache is repairable; no database/request details logged.
    deadline = time.monotonic() + 180
    compressed = expanded = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.tmp', delete=False) as out:
            compressed = Path(out.name)
            request = urllib.request.Request(
                'https://download.db-ip.com/free/dbip-city-lite-' + month + '.mmdb.gz',
                headers={'User-Agent': 'dynacat-geoip/1.0'})
            with fetch(request, timeout=30) as response:
                size = 0
                while chunk := response.read(1024 * 1024):
                    if time.monotonic() > deadline:
                        raise TimeoutError('Database download deadline exceeded')
                    size += len(chunk)
                    if size > compressed_limit:
                        raise ValueError('Compressed database exceeds limit')
                    out.write(chunk)
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.tmp', delete=False) as out:
            expanded = Path(out.name)
            with gzip.open(compressed, 'rb') as source:
                size = 0
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > expanded_limit:
                        raise ValueError('Expanded database exceeds limit')
                    out.write(chunk)
        with maxminddb.open_database(str(expanded)) as reader:
            if reader.metadata().database_type != 'DBIP-City-Lite':
                raise ValueError('Unexpected database type')
        os.chmod(expanded, 0o644)
        os.replace(expanded, target)
        return 'updated'
    finally:
        for path in (compressed, expanded):
            if path is not None:
                path.unlink(missing_ok=True)


def database_current(directory, month):
    """Offline health predicate for the explicitly requested monthly database."""
    import maxminddb
    try:
        with maxminddb.open_database(str(Path(directory) / 'dbip-city-lite.mmdb')) as reader:
            metadata = reader.metadata()
            return (metadata.database_type == 'DBIP-City-Lite'
                    and datetime.fromtimestamp(metadata.build_epoch, timezone.utc).strftime('%Y-%m') == month)
    except Exception:
        return False


def watch_database(directory, month, *, stop=None, updater=None, emit=None):
    """Periodically validate/repair the cache; successful checks do not download."""
    import threading
    stop = stop or threading.Event()
    updater = updater or update_database
    emit = emit or (lambda message: print(message, flush=True))
    while not stop.is_set():
        try:
            emit('Database ' + updater(directory, month))
        except Exception:
            emit('Database update failed; previous database retained if present')
        stop.wait(3600)


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--month', required=True, help='Explicit DB-IP release YYYY-MM')
    parser.add_argument('--directory', default='/geoip')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--watch', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.check:
            healthy = database_current(args.directory, args.month)
            print('Database current' if healthy else 'Current database unavailable')
            sys.exit(0 if healthy else 1)
        elif args.watch:
            watch_database(args.directory, args.month)
        else:
            print('Database ' + update_database(args.directory, args.month))
    except Exception:
        print('Database update failed; previous database retained if present', file=sys.stderr)
        sys.exit(1)
