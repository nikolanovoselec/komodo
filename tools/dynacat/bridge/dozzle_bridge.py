#!/usr/bin/env python3
"""Read-only adapter: Dozzle SSE -> compact JSON for Dynacat custom-api widgets."""
import json
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DOZZLE_EVENTS = "https://dozzle.local.graymatter.ch/api/events/stream"


def dozzle_snapshot():
    request = urllib.request.Request(DOZZLE_EVENTS, headers={
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "User-Agent": "dynacat-dozzle-bridge/1.0",
    })
    event = None
    data = []
    with urllib.request.urlopen(request, timeout=12) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                event = line.partition(":")[2].strip()
                data = []
            elif line.startswith("data:"):
                data.append(line.partition(":")[2].strip())
            elif not line and event == "containers-changed" and data:
                containers = json.loads("\n".join(data))
                return summarise(containers)
    raise RuntimeError("Dozzle did not return an initial container snapshot")


def summarise(containers):
    states = Counter(c.get("state", "unknown") for c in containers)
    rows = []
    total_cpu = 0.0
    total_memory = 0
    for c in containers:
        stats = (c.get("stats") or [{}])[-1]
        cpu = float(stats.get("cpu") or 0)
        memory = int(stats.get("memoryUsage") or 0)
        total_cpu += cpu
        total_memory += memory
        rows.append({
            "name": c.get("name", "unknown"),
            "state": c.get("state", "unknown"),
            "cpu": round(cpu, 1),
            "memory_mb": round(memory / 1048576, 1),
        })
    rows.sort(key=lambda r: (r["cpu"], r["memory_mb"]), reverse=True)
    return {
        "total": len(containers),
        "running": states["running"],
        "stopped": len(containers) - states["running"],
        "hosts": len({c.get("host") for c in containers if c.get("host")}),
        "cpu": round(total_cpu, 1),
        "memory_mb": round(total_memory / 1048576, 1),
        "top": rows[:8],
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/dozzle", "/health"):
            self.send_error(404)
            return
        try:
            payload = {"ok": True} if self.path == "/health" else dozzle_snapshot()
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": "Dozzle telemetry unavailable"}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *_):
        pass


ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()
