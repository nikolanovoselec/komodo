"""Secret-reference contract; never reads protected credential values."""
from pathlib import Path
import tomllib
import yaml

ROOT = Path(__file__).parent

def test_pihole_secret_is_wired_only_to_collector():
    resources = tomllib.loads((ROOT.parents[1] / 'komodo_core/main.toml').read_text())
    stack = next(s for s in resources['stack'] if s['name'] == 'tools_dynacat')
    assert 'PIHOLE_API_KEY = [[PIHOLE_API_KEY]]' in stack['config']['environment']
    compose = yaml.safe_load((ROOT/'compose.yaml').read_text())
    assert compose['services']['workload-summary']['environment']['PIHOLE_API_KEY'] == '${PIHOLE_API_KEY}'
    assert all('PIHOLE_API_KEY' not in s.get('environment', {}) for n,s in compose['services'].items() if n != 'workload-summary')
