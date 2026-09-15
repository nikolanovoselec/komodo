import importlib.util
import pathlib
import json
from datetime import datetime, timezone

SITE = "88f7af54-98f8-306a-a1c7-c9349722b1f6"
DEVICE = "4225ccb2-ef09-3b91-a6fe-2114de727d0f"
NOW = 1800000000


def source(path):
    path = path.split("?")[0]
    table = {
        "info": {"applicationVersion": "10.4.57"},
        "sites": [{"id": SITE, "name": "Default"}],
        f"sites/{SITE}/devices": [
            {
                "id": DEVICE,
                "name": "UDM SE",
                "model": "UniFi Dream Machine PRO SE",
                "state": "ONLINE",
                "features": ["switching"],
            }
        ],
        f"sites/{SITE}/clients": [
            {
                "id": "client",
                "name": "Laptop",
                "type": "WIRELESS",
                "uplinkDeviceId": DEVICE,
                "macAddress": "omit-me",
            }
        ],
        f"sites/{SITE}/networks": [
            {"id": "network", "name": "Guest", "vlanId": 4, "enabled": True}
        ],
        f"sites/{SITE}/wifi/broadcasts": [
            {
                "id": "wifi",
                "name": "Guest",
                "enabled": True,
                "securityConfiguration": {
                    "type": "WPA2_PERSONAL",
                    "password": "secret",
                },
                "broadcastingFrequenciesGHz": [2.4, 5],
            }
        ],
        f"sites/{SITE}/wans": [{"id": "wan", "name": "Internet 1"}],
        f"sites/{SITE}/networks/network": {
            "ipv4Configuration": {
                "hostIpAddress": "192.168.4.1",
                "prefixLength": 24,
                "dhcpConfiguration": {"password": "never-pass"},
            }
        },
        f"sites/{SITE}/firewall/policies": [],
        f"sites/{SITE}/firewall/zones": [],
        f"sites/{SITE}/acl-rules": [],
        f"sites/{SITE}/devices/{DEVICE}": {
            "uplink": {"deviceId": "upstream"},
            "interfaces": {
                "ports": [
                    {
                        "idx": 1,
                        "state": "UP",
                        "speedMbps": 1000,
                        "poe": {"state": "UP", "enabled": True},
                    },
                    {"state": "DOWN"},
                ],
                "radios": [{"frequencyGHz": 5, "channel": 40, "channelWidthMHz": 80}],
            },
        },
        f"sites/{SITE}/devices/{DEVICE}/statistics/latest": {
            "uptimeSec": 123,
            "cpuUtilizationPct": 25,
            "memoryUtilizationPct": 60,
            "lastHeartbeatAt": datetime.fromtimestamp(
                NOW - 10, timezone.utc
            ).isoformat(),
            "uplink": {"rxRateBps": 123000000, "txRateBps": 5000000},
        },
    }
    data = table[path]
    return (
        dict(offset=0, limit=100, count=len(data), totalCount=len(data), data=data)
        if isinstance(data, list)
        else data
    )


def test_live_projection_is_allowlisted_and_history_uses_source_time():
    u = module()
    from workload_history import Store

    result = u.collect(source, store=Store(), now=NOW)
    assert result["state"] == "available"
    assert result["summary"] == dict(
        devices_total=1,
        devices_online=1,
        clients_total=1,
        clients_wired=0,
        clients_wireless=1,
        networks_total=1,
        wifi_total=1,
    )
    d = result["devices"][0]
    assert (
        d["kind"],
        d["rx_mbps"],
        d["tx_mbps"],
        d["cpu_percent"],
        d["ports_active"],
        d["ports_total"],
        d["clients_count"],
    ) == ("gateway", 123, 5, 25, 1, 2, 1)
    assert d["history"]["rx"]["samples"] == 1
    assert d["history"]["rx"]["scale"] == d["history"]["tx"]["scale"] == 123
    assert d["source_timestamp"] == NOW - 10
    assert result["clients"][0]["signal_dbm"] is None
    assert result["wan"]["available"] is False
    assert result["wifi"][0]["security"] == "WPA2_PERSONAL"
    assert "secret" not in json.dumps(result)
    assert "omit-me" not in json.dumps(result)
    assert result["partial"] is False


import pytest
import hashlib
import threading


def test_network_details_and_topology_are_explicit_and_sanitized():
    u = module()
    r = u.collect(source, now=NOW)
    assert r["networks"][0]["subnet"] == "192.168.4.0/24"
    assert r["devices"][0]["ports"][0]["speed_mbps"] == 1000
    assert r["devices"][0]["radios"][0]["channel"] == 40
    assert r["devices"][0]["uplink_device_id"] == "upstream"
    assert r["firewall"]["available"] and r["firewall"]["rules"] == []
    assert "never-pass" not in json.dumps(r)


def test_unsupported_zone_firewall_is_explained_without_lying_about_legacy_rules():
    u = module()

    def get(path):
        if "/firewall/" in path:
            raise u.Unsupported("Zone Based Firewall is not configured")
        return source(path)

    r = u.collect(get, now=NOW)
    assert r["firewall"]["available"] is False
    assert "not configured" in r["firewall"]["reason"]
    assert r["partial"] is False


def test_device_optional_detail_failure_preserves_inventory_and_other_metrics():
    u = module()

    def get(path):
        if path.endswith("/devices/" + DEVICE):
            raise RuntimeError("do not echo")
        return source(path)

    r = u.collect(get, now=NOW)
    assert r["partial"]
    assert r["devices"][0]["cpu_percent"] == 25
    assert r["devices"][0]["ports_total"] is None


def test_network_route_is_independent_of_current_and_pve(monkeypatch):
    import adapter
    import urllib.request

    u = module()
    monkeypatch.setattr(
        u, "current", lambda: dict(state="available", devices=[]), raising=False
    )
    server = adapter.make_server(
        ("127.0.0.1", 0), lambda: pytest.fail("must not collect Komodo")
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/network-current", timeout=1
        )
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert json.load(response)["state"] == "available"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_current_is_nonblocking_pump_for_central_scheduler(monkeypatch):
    u = module()
    service = u.UniFiSource(loader=lambda: u.collect(source, now=NOW))
    monkeypatch.setattr(u, "_SOURCE", service, raising=False)
    r = u.current()
    assert r["state"] in ("starting", "available")
    service.worker.join(2)
    assert u.current()["state"] == "available"


def test_history_retains_source_samples_without_overwriting_on_stale_poll():
    u = module()
    from workload_history import Store

    store = Store()
    u.collect(source, store=store, now=NOW)
    r = u.collect(source, store=store, now=NOW + 200)
    assert r["devices"][0]["cpu_percent"] is None
    assert r["devices"][0]["history"]["cpu"]["samples"] == 1


def test_refresh_start_does_not_make_old_data_fresh_again():
    u = module()
    clock = [0]
    service = u.UniFiSource(
        loader=lambda: u.collect(source, now=NOW), clock=lambda: clock[0]
    )
    service.refresh()
    service.worker.join(2)
    entered, release = threading.Event(), threading.Event()

    def blocked():
        entered.set()
        release.wait(2)
        return u.collect(source, now=NOW)

    service.loader = blocked
    clock[0] = 31
    service.refresh()
    assert entered.wait(1)
    assert service.snapshot()["state"] == "stale"
    release.set()
    service.worker.join(2)


def test_metadata_cache_does_not_cache_clients_devices_or_live_statistics():
    u = module()
    calls = []
    clock = [0]
    cache = u.MetadataCache(clock=lambda: clock[0])

    def get(path):
        calls.append(path)
        return {"ok": True}

    for path in ["info", f"sites/{SITE}/networks?offset=0&limit=100"]:
        cache.get(get, path)
        cache.get(get, path)
        assert calls.count(path) == 1
    for path in [
        f"sites/{SITE}/clients?offset=0&limit=100",
        f"sites/{SITE}/devices?offset=0&limit=100",
        f"sites/{SITE}/devices/{DEVICE}/statistics/latest",
    ]:
        cache.get(get, path)
        cache.get(get, path)
        assert calls.count(path) == 2
    clock[0] = 61
    cache.get(get, "info")
    assert calls.count("info") == 2


def test_transport_wall_deadline_interrupts_a_trickling_body(monkeypatch):
    u = module()
    clock = [0]
    interrupted = threading.Event()

    class Socket:
        def getpeercert(self, binary_form=False):
            return b"cert"

        def settimeout(self, value):
            pass

        def shutdown(self, how):
            interrupted.set()

    class Response:
        status = 200

        def read(self, limit):
            assert interrupted.wait(
                0.3
            ), "whole-response deadline must interrupt socket"
            raise TimeoutError("interrupted")

    class Connection:
        sock = Socket()

        def connect(self):
            pass

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setenv("DYNACAT_UNIFI_TOKEN", "unit-secret")
    client = u.Client(
        pin=hashlib.sha256(b"cert").hexdigest(),
        clock=lambda: clock[0],
        connection_factory=lambda *a, **k: Connection(),
    )
    clock[0] = 19.98
    with pytest.raises(TimeoutError):
        client("info")


def test_invalid_percentages_are_not_presented_and_history_persists(tmp_path):
    u = module()
    from workload_history import Store

    def bad(path):
        result = source(path)
        if path.endswith("statistics/latest"):
            result["cpuUtilizationPct"] = 101
            result["memoryUtilizationPct"] = float("nan")
        return result

    store = Store(str(tmp_path / "history.sqlite"))
    r = u.collect(bad, store=store, now=NOW)
    assert r["devices"][0]["cpu_percent"] is None
    assert r["devices"][0]["memory_percent"] is None
    del store
    r = u.collect(source, store=Store(str(tmp_path / "history.sqlite")), now=NOW + 10)
    assert r["devices"][0]["history"]["rx"]["samples"] == 1


def test_source_refresh_is_nonblocking_single_flight_and_expired_data_is_hidden():
    u = module()
    entered, release = threading.Event(), threading.Event()
    count = []
    clock = [0]

    def load():
        count.append(1)
        entered.set()
        release.wait(2)
        return u.collect(source, now=NOW)

    service = u.UniFiSource(loader=load, clock=lambda: clock[0])
    service.refresh()
    assert entered.wait(1)
    service.refresh()
    assert len(count) == 1
    assert service.snapshot()["state"] == "starting"
    release.set()
    service.worker.join(2)
    assert service.snapshot()["state"] == "available"
    clock[0] = 31
    r = service.snapshot()
    assert r["state"] == "stale" and r["devices"] == []
    assert r["summary"]["devices_online"] is None


def test_source_failed_refresh_does_not_leak_exception_or_healthy_old_data():
    u = module()
    service = u.UniFiSource(
        loader=lambda: (_ for _ in ()).throw(RuntimeError("private-token"))
    )
    service.refresh()
    service.worker.join(2)
    r = service.snapshot()
    assert r["state"] == "error" and r["partial"]
    assert "private-token" not in json.dumps(r)


def test_transport_pins_before_sending_token_and_rejects_all_other_paths(monkeypatch):
    u = module()
    events = []

    class Socket:
        def getpeercert(self, binary_form=False):
            return b"public certificate"

        def settimeout(self, value):
            assert 0 < value <= 4

    class Response:
        status = 200

        def read(self, limit):
            return b'{"applicationVersion":"10.4.57"}'

    class Connection:
        sock = Socket()

        def connect(self):
            events.append("connect")

        def request(self, method, path, headers):
            events.append((method, path, headers))

        def getresponse(self):
            return Response()

        def close(self):
            events.append("close")

    monkeypatch.setenv("DYNACAT_UNIFI_TOKEN", "unit-secret")
    factory = lambda *a, **k: Connection()
    client = u.Client(
        pin=hashlib.sha256(b"public certificate").hexdigest(),
        connection_factory=factory,
    )
    assert client("info")["applicationVersion"] == "10.4.57"
    assert events[0] == "connect" and events[1][0] == "GET"
    for path in [
        "https://evil.test",
        "../foo",
        "sites/" + SITE + "/devices/" + DEVICE + "/actions",
        "info?evil=1",
    ]:
        with pytest.raises(ValueError):
            client(path)
    events.clear()
    with pytest.raises(Exception):
        u.Client(pin="00" * 32, connection_factory=factory)("info")
    assert not any(isinstance(e, tuple) for e in events)


def test_transport_deadline_prevents_unbounded_optional_work(monkeypatch):
    u = module()
    monkeypatch.setenv("DYNACAT_UNIFI_TOKEN", "unit-secret")
    clock = [0]
    client = u.Client(
        clock=lambda: clock[0],
        connection_factory=lambda *a, **k: pytest.fail("deadline must prevent socket"),
    )
    clock[0] = 21
    with pytest.raises(TimeoutError):
        client("info")


def test_optional_failure_is_partial_not_fake_empty_healthy_counts():
    u = module()

    def broken(path):
        if "/clients?" in path:
            raise RuntimeError("secret upstream response")
        return source(path)

    r = u.collect(broken, now=NOW)
    assert r["state"] == "available" and r["partial"]
    assert r["summary"]["clients_total"] is None
    assert r["summary"]["clients_wired"] is None
    assert r["devices"][0]["clients_count"] is None
    assert r["endpoints"]["clients"]["state"] == "error"
    assert "secret upstream" not in json.dumps(r)


@pytest.mark.parametrize(
    "bad",
    [
        dict(
            offset=0, limit=100, count=1, totalCount=1, data=[{"id": "a"}, {"id": "b"}]
        ),
        dict(offset=1, limit=100, count=1, totalCount=1, data=[{"id": "a"}]),
        dict(offset=0, limit=100, count=0, totalCount=2, data=[]),
    ],
)
def test_malformed_pagination_never_claims_complete(bad):
    u = module()
    rows, meta = u.paginate(lambda _: bad, "sites")
    assert meta["partial"] and meta["state"] == "error"


def test_stale_missing_future_and_invalid_source_timestamp_never_look_current():
    u = module()
    for timestamp in [
        None,
        "nonsense",
        datetime.fromtimestamp(NOW + 30, timezone.utc).isoformat(),
        datetime.fromtimestamp(NOW - 301, timezone.utc).isoformat(),
    ]:

        def stale(path):
            result = source(path)
            if path.endswith("statistics/latest"):
                result["lastHeartbeatAt"] = timestamp
            return result

        r = u.collect(stale, now=NOW)
        d = r["devices"][0]
        assert d["cpu_percent"] is None
        assert d["rx_mbps"] is None
        assert d["metrics_state"] in ("stale", "unavailable")


def module():
    assert (
        pathlib.Path(__file__).with_name("unifi.py").exists()
    ), "UniFi backend not implemented"
    import unifi

    return unifi


def test_pagination_is_bounded_and_marks_partial():
    u = module()
    calls = []

    def get(path):
        calls.append(path)
        offset = (len(calls) - 1) * 2
        return dict(
            offset=offset,
            limit=2,
            count=2,
            totalCount=8,
            data=[{"id": str(offset)}, {"id": str(offset + 1)}],
        )

    rows, meta = u.paginate(get, "sites", page_size=2, max_pages=2)
    assert len(rows) == 4
    assert meta == dict(state="available", partial=True, total=8, returned=4)
    assert calls == ["sites?offset=0&limit=2", "sites?offset=2&limit=2"]
