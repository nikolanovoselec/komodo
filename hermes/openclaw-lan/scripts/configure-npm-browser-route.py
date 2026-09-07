#!/usr/bin/env python3
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


database = Path("/docker/configs/npm/data/database.sqlite")
nginx_config = Path("/docker/configs/npm/data/nginx/proxy_host/84.conf")
location = {
    "path": "/browser/",
    "advanced_config": "rewrite ^/browser/(.*)$ /$1 break;",
    "forward_scheme": "http",
    "forward_host": "openclaw.lan",
    "forward_port": 6080,
}

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = database.with_name(f"database.sqlite.hermes-browser-{stamp}.bak")
shutil.copy2(database, backup)

with sqlite3.connect(database) as connection:
    row = connection.execute(
        "SELECT locations FROM proxy_host WHERE id = 84"
    ).fetchone()
    if row is None:
        raise SystemExit("Nginx Proxy Manager proxy host 84 does not exist")
    locations = json.loads(row[0] or "[]")
    locations = [entry for entry in locations if entry.get("path") != "/browser/"]
    locations.append(location)
    connection.execute(
        "UPDATE proxy_host SET locations = ?, modified_on = datetime('now') WHERE id = 84",
        (json.dumps(locations, separators=(",", ":")),),
    )

text = nginx_config.read_text()
marker = "  # Hermes persistent browser\n"
block = """  # Hermes persistent browser
  location ^~ /browser/ {
    rewrite ^/browser/(.*)$ /$1 break;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Scheme $scheme;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_http_version 1.1;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_pass http://openclaw.lan:6080;
  }

"""
if marker not in text:
    needle = "  location / {\n"
    if needle not in text:
        raise SystemExit("could not locate the default proxy location")
    nginx_config.write_text(text.replace(needle, block + needle, 1))

print(f"Configured /browser/ on proxy host 84; database backup: {backup}")
