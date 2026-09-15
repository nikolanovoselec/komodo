"""One-shot DB-IP Lite updater; only the database URL is fetched, never an IP."""
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


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--month', required=True, help='Explicit DB-IP release YYYY-MM')
    parser.add_argument('--directory', default='/geoip')
    args = parser.parse_args()
    try:
        print('Database ' + update_database(args.directory, args.month))
    except Exception:
        print('Database update failed; previous database retained if present', file=sys.stderr)
        sys.exit(1)
