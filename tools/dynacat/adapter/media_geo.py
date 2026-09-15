"""Offline-only IP location. No HTTP lookup endpoint or network lookup code."""
import ipaddress
import os
import threading


class GeoLocator:
    def __init__(self, path):
        self.path = path
        self._reader = None
        self._signature = None
        self._lock = threading.Lock()

    def locate(self, address, relayed=False):
        if relayed in (True, 1, '1', 'true'):
            return {'label': 'Relay · location unknown', 'status': 'relay'}
        try:
            ip = ipaddress.ip_address(address)
        except (ValueError, TypeError):
            return {'label': 'Location unknown', 'status': 'unknown'}
        if not ip.is_global or ip.is_multicast:
            return {'label': 'Local network', 'status': 'local'}
        try:
            import maxminddb
            with self._lock:
                stat = os.stat(self.path)
                signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
                if self._reader is None or signature != self._signature:
                    if self._reader is not None:
                        self._reader.close()
                        self._reader = None
                    self._reader = maxminddb.open_database(self.path)
                    self._signature = signature
                data = self._reader.get(str(ip)) or {}
            city = data.get('city', {}).get('names', {}).get('en', '')
            country = data.get('country', {}).get('names', {}).get('en', '')
            label = ', '.join(v for v in (city, country) if v)
            if label:
                return {'label': '≈ ' + label, 'status': 'approximate'}
        except Exception:
            pass  # Never log exception text: reader errors may contain the address.
        return {'label': 'Location unavailable', 'status': 'unavailable'}
