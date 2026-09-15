"""Bounded, read-only official UniFi Network Integration projection."""

import os
import re
import json
import ssl
import hashlib
import hmac
import http.client
import time
import threading
import copy
import ipaddress
from datetime import datetime
from workload_history import Store, chart, number

SITE = "88f7af54-98f8-306a-a1c7-c9349722b1f6"
_STORE = None
# TOFU public certificate fingerprint collected via authenticated SSH over LAN.
PIN = "9c:24:23:e4:df:3e:ba:16:5f:10:8d:a3:77:1e:d4:f9:19:e7:3f:c9:97:4f:36:60:6d:b6:b5:68:23:cc:33:10"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
LIST = rf"(?:sites|sites/{SITE}/(?:devices|clients|networks|wifi/broadcasts|wans|firewall/policies|firewall/zones|acl-rules))\?offset=\d{{1,4}}&limit=(?:[1-9]\d?|100)"
DETAIL = rf"sites/{SITE}/(?:devices/{UUID}(?:/statistics/latest)?|networks/{UUID})"


class Unsupported(Exception):
    pass


class Client:
    """Fixed gateway, exact certificate pin before credentials, no redirects.

    No process-wide SSL overrides. Trust is this one public certificate, not its
    unifi.local hostname. A certificate change fails closed until pin review.
    """

    def __init__(self, pin=None, connection_factory=None, clock=time.monotonic):
        self.pin = (
            (pin or os.environ.get("DYNACAT_UNIFI_CERT_SHA256", PIN))
            .replace(":", "")
            .lower()
        )
        if not re.fullmatch("[0-9a-f]{64}", self.pin):
            raise ValueError("Invalid UniFi certificate pin")
        self.clock, self.deadline = clock, clock() + 20
        self.factory = connection_factory or http.client.HTTPSConnection

    def __call__(self, path):
        if path != "info" and not re.fullmatch(f"(?:{LIST}|{DETAIL})", path):
            raise ValueError("Read path not allowed")
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("UniFi collection deadline exceeded")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # compensated by exact pin BEFORE request
        conn = self.factory(
            "192.168.1.1", 443, timeout=min(4, remaining), context=context
        )
        timer = None
        try:
            conn.connect()
            actual = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
            if not hmac.compare_digest(actual, self.pin):
                raise ssl.SSLError("UniFi certificate pin mismatch")
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                raise TimeoutError("UniFi collection deadline exceeded")
            conn.sock.settimeout(min(4, remaining))
            # Socket timeout alone permits an indefinitely trickling response.
            # Shut down this exact socket when the collection wall budget expires.
            sock = conn.sock

            def interrupt():
                try:
                    sock.shutdown(2)
                except OSError:
                    pass

            timer = threading.Timer(remaining, interrupt)
            timer.daemon = True
            timer.start()
            conn.request(
                "GET",
                "/proxy/network/integration/v1/" + path,
                headers={
                    "X-API-KEY": os.environ["DYNACAT_UNIFI_TOKEN"],
                    "Accept": "application/json",
                },
            )
            response = conn.getresponse()
            if response.status == 400:
                error = json.loads(response.read(4096))
                if (
                    error.get("code")
                    == "api.firewall.zone-based-firewall-not-configured"
                ):
                    raise Unsupported("Zone Based Firewall is not configured")
            if response.status != 200:
                raise ValueError("UniFi read unavailable")
            payload = response.read(2_000_001)
            if len(payload) > 2_000_000 or self.clock() > self.deadline:
                raise ValueError("UniFi response limit exceeded")
            result = json.loads(payload)
            if not isinstance(result, dict):
                raise ValueError("UniFi invalid response")
            return result
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()


class MetadataCache:
    """Bounded 60s metadata cache; never cache live clients/device lists/stats."""

    def __init__(self, clock=time.monotonic):
        self.clock, self.entries = clock, {}
        self.lock = threading.Lock()

    def get(self, read, path):
        dynamic = "/statistics/latest" in path or re.search(
            r"/(?:clients|devices)\?", path
        )
        if dynamic:
            return read(path)
        with self.lock:
            entry = self.entries.get(path)
            if entry and self.clock() - entry[0] < 60:
                if entry[2]:
                    raise Unsupported("Zone Based Firewall is not configured")
                return copy.deepcopy(entry[1])
        try:
            data, unsupported = read(path), False
        except Unsupported:
            data, unsupported = None, True
        with self.lock:
            self.entries[path] = (self.clock(), data, unsupported)
            while len(self.entries) > 256:
                self.entries.pop(next(iter(self.entries)))
        if unsupported:
            raise Unsupported("Zone Based Firewall is not configured")
        return copy.deepcopy(data)


_METADATA = MetadataCache()


class UniFiSource:
    """Nonblocking lifecycle hooks for the central background collector.

    Call refresh() every five seconds independently of HTTP traffic. It starts
    at most one flight, cooling down five seconds after success OR failure.
    snapshot() never starts upstream I/O; collection-start age gates stale data.
    """

    def __init__(self, loader=None, clock=time.monotonic):
        self.loader, self.clock = loader or collect, clock
        self.lock = threading.Lock()
        self.worker = None
        self.started = self.completed = self.data_started = None
        self.data = None
        self.failed = False

    def refresh(self):
        with self.lock:
            now = self.clock()
            if self.worker is not None and self.worker.is_alive():
                return
            if self.completed is not None and now - self.completed < 5:
                return
            self.started = now
            self.worker = threading.Thread(
                target=self._run, daemon=True, name="unifi-current"
            )
            self.worker.start()

    def _run(self):
        try:
            data = self.loader()
            json.dumps(data, allow_nan=False)
            failed = bool(data.get("error"))
        except Exception:
            data, failed = None, True
        with self.lock:
            self.data, self.failed, self.completed = data, failed, self.clock()
            self.data_started = self.started

    def snapshot(self):
        with self.lock:
            age = (
                None if self.data_started is None else self.clock() - self.data_started
            )
            state = (
                "error"
                if self.failed
                else (
                    "starting"
                    if self.data is None
                    else "stale" if age is not None and age >= 30 else "available"
                )
            )
            freshness = dict(
                age_seconds=age,
                max_age_seconds=30,
                age_basis="collection_started",
                collecting=self.worker is not None and self.worker.is_alive(),
            )
            if state == "available":
                return dict(copy.deepcopy(self.data), freshness=freshness)
            return dict(
                state=state,
                error=(
                    None
                    if state == "starting"
                    else "UniFi telemetry unavailable; verify gateway read access and certificate pin"
                ),
                site=dict(id=SITE, name=None),
                summary={
                    k: None
                    for k in (
                        "devices_total",
                        "devices_online",
                        "clients_total",
                        "clients_wired",
                        "clients_wireless",
                        "networks_total",
                        "wifi_total",
                    )
                },
                devices=[],
                clients=[],
                networks=[],
                wifi=[],
                wan=dict(
                    available=False,
                    state="unavailable",
                    rx_mbps=None,
                    tx_mbps=None,
                    reason="No current source",
                ),
                capabilities=[],
                partial=True,
                freshness=freshness,
            )


# Instantiated after collect() is defined at the bottom of this module.


def collect(get=None, store=None, now=None):
    global _STORE
    now = time.time() if now is None else now
    if store is None:
        if _STORE is None:
            _STORE = Store(os.environ.get("UNIFI_HISTORY_PATH", ":memory:"))
        store = _STORE
    if get is None:
        client = Client()
        get = lambda path: _METADATA.get(client, path)
    version = get("info").get("applicationVersion")
    sites, _ = paginate(get, "sites")
    site = next(s for s in sites if s["id"] == SITE)
    prefix = f"sites/{SITE}/"
    data, endpoints = {}, {}
    for name, path in [
        ("devices", "devices"),
        ("clients", "clients"),
        ("networks", "networks"),
        ("wifi", "wifi/broadcasts"),
        ("wans", "wans"),
        ("firewall", "firewall/policies"),
        ("zones", "firewall/zones"),
        ("acl", "acl-rules"),
    ]:
        data[name], endpoints[name] = paginate(get, prefix + path)

    def optional(path):
        try:
            result = get(prefix + path)
            if not isinstance(result, dict):
                raise ValueError("Invalid detail")
            return result
        except Exception:
            endpoints[path] = dict(state="error", partial=True, total=None, returned=0)
            return {}

    clients = [
        dict(
            id=c.get("id"),
            name=c.get("name"),
            kind={"WIRED": "wired", "WIRELESS": "wireless"}.get(c.get("type"), "other"),
            ip=c.get("ipAddress"),
            network=None,
            device=c.get("uplinkDeviceId"),
            signal_dbm=None,
            rx_mbps=None,
            tx_mbps=None,
        )
        for c in data["clients"]
    ]
    devices = []
    for raw in data["devices"]:
        identity = raw["id"]
        detail = optional("devices/" + identity) if len(devices) < 32 else {}
        stats = (
            optional("devices/" + identity + "/statistics/latest")
            if len(devices) < 32
            else {}
        )
        if len(devices) >= 32:
            endpoints["device_details"] = dict(
                state="partial", partial=True, total=len(data["devices"]), returned=32
            )
        try:
            stamp = datetime.fromisoformat(
                stats["lastHeartbeatAt"].replace("Z", "+00:00")
            )
            ts = stamp.timestamp() if stamp.tzinfo is not None else None
        except (KeyError, TypeError, ValueError, AttributeError):
            ts = None
        metrics_state = (
            "available"
            if ts is not None and 0 <= now - ts <= 120
            else "stale" if ts is not None and ts <= now else "unavailable"
        )
        if metrics_state != "available":
            stats = {}
        features = raw.get("features") or []
        model = raw.get("model") or ""
        kind = (
            "gateway"
            if (
                "Dream Machine" in model
                or model.startswith(("UDM", "UCG", "UXG", "USG"))
            )
            else (
                "access-point"
                if "accessPoint" in features
                else "switch" if "switching" in features else "other"
            )
        )
        ports = (detail.get("interfaces") or {}).get("ports")
        uplink = stats.get("uplink") or {}
        rx, tx = number(uplink.get("rxRateBps")), number(uplink.get("txRateBps"))
        cpu, ram = number(stats.get("cpuUtilizationPct")), number(
            stats.get("memoryUtilizationPct")
        )
        cpu = cpu if cpu is not None and cpu <= 100 else None
        ram = ram if ram is not None and ram <= 100 else None
        device = dict(
            id=identity,
            name=raw.get("name"),
            model=model,
            kind=kind,
            state=raw.get("state"),
            ip=raw.get("ipAddress"),
            uptime_seconds=number(stats.get("uptimeSec")),
            cpu_percent=cpu,
            memory_percent=ram,
            rx_mbps=rx / 1e6 if rx is not None else None,
            tx_mbps=tx / 1e6 if tx is not None else None,
            ports_active=(
                sum(p.get("state") == "UP" for p in ports)
                if ports is not None
                else None
            ),
            ports_total=len(ports) if ports is not None else None,
            clients_count=sum(c["device"] == identity for c in clients),
            url=None,
            source_timestamp=ts,
            history={},
        )
        device["metrics_state"] = metrics_state
        device["uplink_device_id"] = (detail.get("uplink") or {}).get("deviceId")
        device["ports"] = [
            dict(
                index=p.get("idx"),
                state=p.get("state"),
                connector=p.get("connector"),
                speed_mbps=p.get("speedMbps"),
                max_speed_mbps=p.get("maxSpeedMbps"),
                poe_enabled=(p.get("poe") or {}).get("enabled"),
                poe_state=(p.get("poe") or {}).get("state"),
            )
            for p in (ports or [])
        ]
        device["radios"] = [
            dict(
                frequency_ghz=r.get("frequencyGHz"),
                channel=r.get("channel"),
                channel_width_mhz=r.get("channelWidthMHz"),
                standard=r.get("wlanStandard"),
            )
            for r in (detail.get("interfaces") or {}).get("radios", [])
        ]
        if endpoints["clients"]["partial"]:
            device["clients_count"] = None
        series = {}
        for metric, key in [
            ("cpu", "cpu_percent"),
            ("ram", "memory_percent"),
            ("rx", "rx_mbps"),
            ("tx", "tx_mbps"),
        ]:
            if metrics_state == "available":
                store.add(f"unifi:{SITE}:{identity}", metric, ts, device[key], now)
            series[metric] = store.rows(f"unifi:{SITE}:{identity}", metric, now)
        network_scale = max(
            [0.001]
            + [
                v
                for metric in ("rx", "tx")
                for _, v in series[metric]
                if number(v) is not None
            ]
        )
        for metric, rows in series.items():
            network = metric in ("rx", "tx")
            points = (
                [
                    (t, 100 * v / network_scale if v is not None else None)
                    for t, v in rows
                ]
                if network
                else rows
            )
            device["history"][metric] = dict(
                chart(points, now),
                source="UniFi lastHeartbeatAt",
                persistence_state=store.state,
                unit="Mbps" if network else "%",
            )
            if network:
                device["history"][metric]["scale"] = network_scale
        devices.append(device)
    networks = [
        dict(
            id=n.get("id"),
            name=n.get("name"),
            vlan=n.get("vlanId"),
            subnet=None,
            purpose=n.get("management"),
            enabled=n.get("enabled"),
        )
        for n in data["networks"]
    ]
    for network in networks[:50]:
        detail = optional("networks/" + network["id"])
        v4 = detail.get("ipv4Configuration") or {}
        try:
            network["subnet"] = str(
                ipaddress.ip_network(
                    f"{v4['hostIpAddress']}/{v4['prefixLength']}", strict=False
                )
            )
        except (KeyError, ValueError):
            pass
    if len(networks) > 50:
        endpoints["network_details"] = dict(
            state="partial", partial=True, total=len(networks), returned=50
        )
    wifi = [
        dict(
            id=w.get("id"),
            name=w.get("name"),
            security=(w.get("securityConfiguration") or {}).get("type"),
            bands=w.get("broadcastingFrequenciesGHz"),
            enabled=w.get("enabled"),
        )
        for w in data["wifi"]
    ]
    summary = dict(
        devices_total=len(devices),
        devices_online=sum(d["state"] == "ONLINE" for d in devices),
        clients_total=len(clients),
        clients_wired=sum(c["kind"] == "wired" for c in clients),
        clients_wireless=sum(c["kind"] == "wireless" for c in clients),
        networks_total=len(networks),
        wifi_total=len(wifi),
    )
    for name, keys in [
        ("devices", ["devices_total", "devices_online"]),
        ("clients", ["clients_total", "clients_wired", "clients_wireless"]),
        ("networks", ["networks_total"]),
        ("wifi", ["wifi_total"]),
    ]:
        if endpoints[name]["partial"]:
            for key in keys:
                summary[key] = None
    capabilities = [
        dict(name=name, available=False, reason=reason)
        for name, reason in [
            (
                "wan_health",
                "Official WAN list exposes names only, not health or measured WAN rates",
            ),
            (
                "client_signal_rates",
                "Client list/detail does not expose signal or rates",
            ),
            (
                "client_network",
                "Client list does not expose network identity; no inferred IP join",
            ),
        ]
    ]
    firewall = dict(
        available=endpoints["firewall"]["state"] == "available",
        reason=(
            "Zone Based Firewall is not configured; legacy firewall rules are not exposed by this Integration API"
            if endpoints["firewall"]["state"] == "unavailable"
            else (
                "Official zone-based firewall read"
                if endpoints["firewall"]["state"] == "available"
                else "Firewall read unavailable"
            )
        ),
        rules=[
            dict(
                id=r.get("id"),
                name=r.get("name"),
                enabled=r.get("enabled"),
                action=(
                    (r.get("action") or {}).get("type")
                    if isinstance(r.get("action"), dict)
                    else r.get("action")
                ),
            )
            for r in data["firewall"]
        ],
        acl_count=(
            endpoints["acl"]["total"] if not endpoints["acl"]["partial"] else None
        ),
    )
    capabilities += [
        dict(
            name=k,
            available=e["state"] == "available",
            reason=(
                "Complete read"
                if not e["partial"] and e["state"] == "available"
                else (
                    "Not configured / unsupported"
                    if e["state"] == "unavailable"
                    else "Incomplete or unavailable read"
                )
            ),
        )
        for k, e in endpoints.items()
    ]
    return dict(
        firewall=firewall,
        wan_connections=[
            dict(id=w.get("id"), name=w.get("name")) for w in data["wans"]
        ],
        state="available",
        error=None,
        site=dict(id=site["id"], name=site.get("name")),
        application_version=version,
        summary=summary,
        devices=devices,
        clients=clients,
        networks=networks,
        wifi=wifi,
        wan=dict(
            available=False,
            state="unavailable",
            rx_mbps=None,
            tx_mbps=None,
            reason=capabilities[0]["reason"],
        ),
        capabilities=capabilities,
        partial=any(e["partial"] for e in endpoints.values()),
        endpoints=endpoints,
        collected_at=now,
    )


def paginate(get, path, page_size=100, max_pages=5):
    page_size, max_pages = min(100, max(1, page_size)), min(10, max(1, max_pages))
    rows, total, offset, seen = [], None, 0, set()
    state = "available"
    for _ in range(max_pages):
        try:
            page = get(f"{path}?offset={offset}&limit={page_size}")
            batch = page["data"]
            reported = page["totalCount"]
            if (
                not isinstance(batch, list)
                or type(reported) is not int
                or reported < 0
                or page.get("offset") != offset
                or page.get("count") != len(batch)
                or len(batch) > page_size
                or offset + len(batch) > reported
                or (not batch and offset < reported)
                or (total is not None and total != reported)
            ):
                raise ValueError("Invalid pagination")
            ids = [r["id"] for r in batch]
            if len(set(ids)) != len(ids) or seen.intersection(ids):
                raise ValueError("Duplicate page")
            seen.update(ids)
            total = reported
            rows.extend(batch)
            offset += len(batch)
            if offset >= total:
                break
        except Unsupported:
            return [], dict(state="unavailable", partial=False, total=None, returned=0)
        except Exception:
            state = "error"
            break
    return rows, dict(
        state=state,
        partial=state == "error" or len(rows) != total,
        total=total,
        returned=len(rows),
    )


_SOURCE = UniFiSource()


def current():
    """Nonblocking central-scheduler pump; HTTP is not required for sampling."""
    _SOURCE.refresh()
    return _SOURCE.snapshot()
