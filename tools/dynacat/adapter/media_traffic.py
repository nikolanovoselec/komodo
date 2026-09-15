"""Bounded media-host network history; never per-app or Plex reserved demand.

Verified Periphery v2.3.2 bin/periphery/src/stats/mod.rs sums sysinfo
NetworkData.received()/transmitted(): bytes since refresh, NOT lifetime counters.
Polling is scheduled by wait_until_timelength; refresh_ts is epoch milliseconds.
Rates use the declared polling interval, not elapsed adapter requests (which can
skip source samples). These are interval-normalized measured volumes, not exact
packet-timed rates. No cumulative counter differencing is appropriate here.
"""


import math
import re
import sqlite3
import time
from collections import deque
from contextlib import closing
from threading import Lock


def graph(points, window_seconds, now=None, gap_seconds=30):
    """Shared Mbps scale; null observations break lines, never bridge outages."""
    end = time.time() if now is None else now
    points = [p for p in points if end - window_seconds <= p['ts'] <= end]
    real = [p for p in points if p['rx_mbps'] is not None]
    maximum = max([p[k] for p in real for k in ('rx_mbps', 'tx_mbps')] or [1])
    scale = max(1, math.ceil(maximum * 1.15))
    series = []
    for key in ('rx', 'tx'):
        path, dots, connected = [], [], False
        previous = None
        for p in points:
            if previous is not None and (p['ts'] <= previous or p['ts'] - previous >= gap_seconds):
                connected = False
            previous = p['ts']
            value = p[key + '_mbps']
            if value is None:
                connected = False
                continue
            x = max(0, min(600, 600 * (p['ts'] - end + window_seconds) / window_seconds))
            y = 100 - value / scale * 96
            path.append(f"{'L' if connected else 'M'}{x:.2f},{y:.2f}")
            dots.append(dict(x=round(x,2), y=round(y,2)))
            connected = True
        series.append(dict(key=key, path=' '.join(path), points=dots))
    return dict(series=series, scale_mbps=scale, samples=len(real),
                start_time=end-window_seconds, end_time=end, duration_seconds=window_seconds,
                span_seconds=round(real[-1]['ts']-real[0]['ts']) if real else 0)


class TrafficHistory:
    def __init__(self, max_points=3602, window_seconds=1800, stale_seconds=30, storage_path=None):
        self.points = deque(maxlen=max_points)
        self.window_seconds = window_seconds
        self.stale_seconds = stale_seconds
        self.last_ts = None
        self.lock = Lock()
        self.storage_path = storage_path
        self.persistence_state = 'memory' if storage_path is None else 'ready'
        if storage_path is not None:
            try:
                with closing(sqlite3.connect(storage_path, timeout=.1)) as db, db:
                    db.execute('CREATE TABLE IF NOT EXISTS media_history (position INTEGER PRIMARY KEY, ts REAL, rx REAL, tx REAL)')
                    self.points.extend(dict(ts=ts, rx_mbps=rx, tx_mbps=tx)
                                       for ts, rx, tx in db.execute(
                                           'SELECT ts, rx, tx FROM media_history ORDER BY position'))
                measured = [p['ts'] for p in self.points if p['rx_mbps'] is not None]
                self.last_ts = measured[-1] if measured else None
            except (sqlite3.Error, OSError):
                self.persistence_state = 'unavailable'

    def observe(self, stats, now=None):
        """Call for a verified media host only; pass {} when missing/disabled.

        now and point ts are epoch seconds. Explicit null points break paths;
        they are absence markers, never synthetic traffic measurements.
        """
        now = time.time() if now is None else now
        with self.lock:
            stats = stats if isinstance(stats, dict) else {}
            match = re.fullmatch(r'([1-9][0-9]*)-(sec|min|hr)', str(stats.get('polling_rate', '')))
            interval = int(match[1]) * {'sec': 1, 'min': 60, 'hr': 3600}[match[2]] if match else None
            values = [stats.get(k) for k in ('refresh_ts', 'network_ingress_bytes', 'network_egress_bytes')]
            valid = all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values)
            ts = values[0] / 1000 if valid and values[0] > 0 else None
            age = now - ts if ts is not None else None
            state = 'unavailable' if age is None or age < 0 or interval is None else 'stale' if age >= self.stale_seconds else 'ready'
            rx = tx = None
            if state == 'ready':
                if self.last_ts is not None and ts < self.last_ts:
                    self.points.clear()
                    self.last_ts = None
                rx = stats['network_ingress_bytes'] * 8 / interval / 1e6
                tx = stats['network_egress_bytes'] * 8 / interval / 1e6
                if ts != self.last_ts:
                    # Core cache publishes sampled intervals (~15s here), not every
                    # Periphery measurement. Join real observations only within the
                    # freshness bound; a >=30s gap is explicitly absent, never filled.
                    if self.last_ts is not None and ts - self.last_ts >= self.stale_seconds:
                        self.points.append(dict(ts=self.last_ts + self.stale_seconds, rx_mbps=None, tx_mbps=None))
                    self.points.append(dict(ts=ts, rx_mbps=rx, tx_mbps=tx))
                    self.last_ts = ts
            elif self.points and self.points[-1]['rx_mbps'] is not None:
                self.points.append(dict(ts=now, rx_mbps=None, tx_mbps=None))
            while self.points and (self.points[0]['ts'] < now - self.window_seconds
                                   or self.points[0]['rx_mbps'] is None):
                self.points.popleft()
            if self.storage_path is not None:
                try:
                    with closing(sqlite3.connect(self.storage_path, timeout=.1)) as db, db:
                        db.execute('CREATE TABLE IF NOT EXISTS media_history (position INTEGER PRIMARY KEY, ts REAL, rx REAL, tx REAL)')
                        db.execute('DELETE FROM media_history')
                        db.executemany('INSERT INTO media_history VALUES (?, ?, ?, ?)',
                                       [(i, p['ts'], p['rx_mbps'], p['tx_mbps'])
                                        for i, p in enumerate(self.points)])
                    self.persistence_state = 'ready'
                except (sqlite3.Error, OSError):
                    self.persistence_state = 'unavailable'
            return dict(available=state == 'ready', state=state, rx_mbps=rx, tx_mbps=tx,
                        persistence_state=self.persistence_state,
                        interval_seconds=interval, age_seconds=age, sample_ts=ts,
                        has_age=age is not None and age >= 0, has_interval=interval is not None,
                        warmup=sum(p['rx_mbps'] is not None for p in self.points) < 2,
                        window_seconds=self.window_seconds, points=[dict(p) for p in self.points],
                        graph=graph(list(self.points), self.window_seconds, now=now, gap_seconds=self.stale_seconds),
                        scope='Media host · all interfaces', source='Komodo Periphery',
                        rate_basis='Measured interval bytes / configured polling seconds')
