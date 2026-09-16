import json
from pathlib import Path

import pihole
import pytest


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/pihole-upstreams-history.json').read_text())


def transport_for(capture, calls, config=None):
    def transport(url, pin, method, path, **kwargs):
        calls.append((method, path))
        if method == 'POST':
            return {'session': {'sid': 'test-session', 'valid': True}}
        if method == 'DELETE':
            return None
        if path == '/api/stats/summary':
            return {'queries': {'total': 20, 'blocked': 3}, 'gravity': {'domains_being_blocked': 100}}
        if path == '/api/history':
            return {'history': capture['history']}
        assert path == '/api/config/dns/upstreams'
        if isinstance(config, Exception):
            raise config
        return capture['config'] if config is None else config
    return transport


def test_captured_config_is_projected_per_instance_without_guessing_ports(monkeypatch):
    monkeypatch.setenv('PIHOLE_API_KEY', 'test-password')
    calls = []
    captures = {row['name']: row for row in FIXTURE['instances']}
    result = pihole.collect(lambda name: pihole.fetch_instance(name, transport_for(captures[name], calls)), now=FIXTURE['captured_at'])
    for instance in result['instances']:
        assert instance['configured_upstreams'] == ['8.8.8.8', '8.8.4.4', '1.1.1.1', '1.0.0.1']
        assert instance['upstreams_available'] is True
        assert instance['upstreams_error'] is None
        assert instance['upstreams_truncated'] is False
    assert calls.count(('GET', '/api/config/dns/upstreams')) == 2
    assert calls[-1] == ('DELETE', '/api/auth')


@pytest.mark.parametrize('config', [TimeoutError('SECRET'), {}, {'config': {'dns': {'upstreams': [None]}}}])
def test_upstream_failure_preserves_summary_history_and_redacts(monkeypatch, config):
    monkeypatch.setenv('PIHOLE_API_KEY', 'test-password')
    calls = []
    result = pihole.collect(lambda name: pihole.fetch_instance(name, transport_for(FIXTURE['instances'][0], calls, config)), now=FIXTURE['captured_at'])
    assert result['available'] and not result['partial']
    assert result['total_queries'] == 40
    assert result['query_history']['available']
    for instance in result['instances']:
        assert instance['configured_upstreams'] is None
        assert not instance['upstreams_available']
        assert instance['upstreams_error']
    assert 'SECRET' not in json.dumps(result)
    assert calls[-1] == ('DELETE', '/api/auth')


@pytest.mark.parametrize('values, expected, truncated', [
    (['127.0.0.1#5335', '2001:4860:4860::8888'], ['127.0.0.1#5335', '2001:4860:4860::8888'], False),
    ([], [], False),
    (['1.1.1.1'] * 20, ['1.1.1.1'] * 16, True),
    (['x' * 257], None, False),
    (['1.1.1.1\nSECRET'], None, False),
])
def test_upstream_bounds_preserve_literal_values(monkeypatch, values, expected, truncated):
    monkeypatch.setenv('PIHOLE_API_KEY', 'test-password')
    config = {'config': {'dns': {'upstreams': values}, 'private': 'SECRET'}}
    row = pihole.fetch_instance(pihole.NAMES[0], transport_for(FIXTURE['instances'][0], [], config))
    assert row['configured_upstreams'] == expected
    assert row['upstreams_truncated'] is truncated
    assert 'SECRET' not in json.dumps(row)


def test_failed_instance_upstreams_are_unavailable_not_empty():
    def fail(name):
        raise TimeoutError('SECRET')
    for instance in pihole.collect(fail)['instances']:
        assert instance['configured_upstreams'] is None
        assert instance['upstreams_available'] is False
        assert instance['upstreams_error']
        assert instance['upstreams_truncated'] is False


def test_captured_history_bars_use_common_total_max_and_real_utc_labels():
    from datetime import datetime, timezone
    result = pihole.query_history(FIXTURE['instances'], FIXTURE['captured_at'])
    maximum = max(sum(row['history'][i]['total'] for row in FIXTURE['instances']) for i in range(3))
    assert result['max_total_count'] == maximum
    assert len(result['points']) == 3
    for point in result['points']:
        assert point['label'] == datetime.fromtimestamp(point['timestamp'], timezone.utc).strftime('%H:%M')
        assert point['permitted_percent'] == pytest.approx(point['permitted'] / maximum * 100)
        assert point['blocked_percent'] == pytest.approx(point['blocked'] / maximum * 100)


@pytest.mark.parametrize('rows, expected', [
    ([], []),
    ([{'history': [{'timestamp': 1500, 'total': 10, 'blocked': 2}]}], [(None, None)]),
    ([{'history': [{'timestamp': 1500, 'total': 0, 'blocked': 0}]}] * 2, [(0, 0)]),
])
def test_bar_empty_partial_and_zero_bins_preserve_null_semantics(rows, expected):
    result = pihole.query_history(rows, 3000)
    assert [(p['permitted_percent'], p['blocked_percent']) for p in result['points']] == expected
    assert result['max_total_count'] == 0
