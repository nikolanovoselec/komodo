"""Synthetic fixtures only: never contact Komodo or PVE."""
import copy
import unittest
from unittest.mock import patch
from typing import Any
import workload_docker
from vm_metrics import VERIFIED_BINDINGS
from navigation import LXC_BINDINGS

NOW = 1800000000


def fixture(kind='qemu', guest_id=102) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    binding = (VERIFIED_BINDINGS if kind == 'qemu' else LXC_BINDINGS)[guest_id]
    server = dict(id=binding[1], name='synthetic-host', info=dict(
        address=binding[2], state='Ok', stats=dict(refresh_ts=NOW * 1000 - 1000)))
    guest = dict(type=kind, id=guest_id, name=binding[0], status='running',
                 cpu=3, ram={'percent': 17}, disk={'percent': 9}, url='/pve-test')
    row = dict(name='synthetic-container', server_id=binding[1], host='synthetic-host',
               state='running', status='Up', cpu=120., ram_bytes=1024,
               ram='1 KiB', url='https://komodo.graymatter.ch/servers/' + binding[1] + '/container/synthetic-container')
    summary = dict(pve=dict(guest_inventory=[guest], nodes=[{'cpu': 42}]),
                   container_inventory=[row], stack_problems=[], definition_issues=[])
    return summary, [server]


class WorkloadDockerTests(unittest.TestCase):
    def enrich(self, summary, servers):
        with patch('workload_docker.time.time', return_value=NOW):
            workload_docker.enrich(summary, servers)
        return summary['pve']['guest_inventory'][0].get('docker')

    def test_verified_mapping_preserves_every_pve_field(self):
        for kind, guest_id in [('qemu', 102), ('lxc', 101)]:
            with self.subTest(kind=kind):
                summary, servers = fixture(kind, guest_id)
                before = copy.deepcopy(summary['pve'])
                docker = self.enrich(summary, servers)
                self.assertTrue(docker['available'])
                self.assertEqual(docker['running'], 1)
                self.assertEqual(docker['cpu'], 120.)
                self.assertEqual(docker['containers'][0]['url'], summary['container_inventory'][0]['url'])
                restored = copy.deepcopy(summary['pve'])
                del restored['guest_inventory'][0]['docker']
                self.assertEqual(restored, before)

    def test_missing_stale_or_bad_host_never_reports_healthy_zero(self):
        for age, state, inventory, label in [
            (30000, 'Ok', True, 'Stale Docker data'),
            (30001, 'Ok', True, 'Stale Docker data'),
            (-1, 'Ok', True, 'Stale Docker data'),
            (None, 'Ok', True, 'Stale Docker data'),
            (float('nan'), 'Ok', True, 'Stale Docker data'),
            (1000, 'NotOk', True, 'Docker host unavailable'),
            (1000, 'Ok', False, 'No Docker data')]:
            with self.subTest(age=age, state=state):
                summary, servers = fixture()
                servers[0]['info']['stats']['refresh_ts'] = None if age is None else NOW * 1000 - age
                servers[0]['info']['state'] = state
                if not inventory:
                    summary['container_inventory'] = []
                summary['stack_problems'] = [dict(id='test-stack', name='test-stack', server_id=servers[0]['id'])]
                docker = self.enrich(summary, servers)
                self.assertFalse(docker['available'])
                self.assertEqual(docker['status'], label)
                self.assertIsNone(docker['running'])
                self.assertIsNone(docker['cpu'])
                self.assertEqual(docker['containers'], [])
                self.assertEqual(len(docker['stack_problems']), 1)

    def test_coverage_nonrunning_unhealthy_sort_and_invalid_numbers(self):
        summary, servers = fixture()
        template = summary['container_inventory'][0]
        summary['container_inventory'] = [dict(template, name=name, state=state, status=status, cpu=cpu, ram_bytes=ram)
            for name, state, status, cpu, ram in [
                ('z-ok', 'running', 'Up healthy', 120, 1024),
                ('a-bad', 'running', 'Up unhealthy', 95, 0),
                ('stopped', 'exited', 'Exited', 999, 999),
                ('missing', 'running', 'Up', None, float('inf')),
                ('invalid', 'running', 'Up', float('nan'), -1),
                ('boolean', 'running', 'Up', True, False)]]
        docker = self.enrich(summary, servers)
        self.assertEqual((docker['running'], docker['total'], docker['failed'], docker['unhealthy']), (5, 6, 1, 1))
        self.assertEqual((docker['cpu'], docker['ram_bytes']), (215, 1024))
        self.assertEqual(docker['cpu_coverage'], {'measured': 2, 'running': 5})
        self.assertEqual(docker['ram_coverage'], {'measured': 2, 'running': 5})
        self.assertEqual({r['name'] for r in docker['containers'][:2]}, {'a-bad', 'stopped'})

    def test_exact_guards_unmatched_and_definitions_unchanged(self):
        for target, key, value in [('guest', 'type', 'lxc'), ('guest', 'id', 999),
                                  ('guest', 'name', 'Servarr'), ('info', 'address', 'https://wrong:8120'),
                                  ('server', 'id', 'replacement')]:
            with self.subTest(target=target, key=key):
                summary, servers = fixture()
                summary['definition_issues'] = [dict(id='unassigned-test', server_id='', name='Definition')]
                definitions = copy.deepcopy(summary['definition_issues'])
                obj = {'guest': summary['pve']['guest_inventory'][0], 'server': servers[0], 'info': servers[0]['info']}[target]
                obj[key] = value
                self.assertIsNone(self.enrich(summary, servers))
                self.assertEqual(len(summary['docker_unmatched']), 1)
                group = summary['docker_unmatched'][0]
                self.assertTrue(group['url'].endswith(summary['container_inventory'][0]['server_id']))
                self.assertEqual(summary['definition_issues'], definitions)

    def test_disabled_hosts_and_their_stacks_never_appear(self):
        summary, servers = fixture()
        servers[0]['info']['state'] = 'Disabled'
        summary['stack_problems'] = [dict(server_id=servers[0]['id'], id='disabled-stack')]
        self.assertIsNone(self.enrich(summary, servers))
        self.assertEqual(summary['docker_unmatched'], [])

    def test_zero_running_is_distinct_from_no_inventory(self):
        summary, servers = fixture()
        summary['container_inventory'][0]['state'] = 'exited'
        docker = self.enrich(summary, servers)
        self.assertTrue(docker['available'])
        self.assertEqual((docker['running'], docker['total']), (0, 1))
        self.assertIsNone(docker['cpu'])
        self.assertEqual(docker['cpu_coverage'], {'measured': 0, 'running': 0})
        summary['container_inventory'] = []
        docker = self.enrich(summary, servers)
        self.assertFalse(docker['available'])
        self.assertIsNone(docker['running'])

    def test_repeated_enrichment_discards_old_data_and_disabled_rows(self):
        summary, servers = fixture()
        self.assertTrue(self.enrich(summary, servers)['available'])
        servers[0]['info']['stats']['refresh_ts'] -= 60000
        self.assertFalse(self.enrich(summary, servers)['available'])
        servers[0]['info']['state'] = 'Disabled'
        self.assertIsNone(self.enrich(summary, servers))
        self.assertEqual(summary['docker_unmatched'], [])

    def test_missing_server_is_unavailable_unmatched_not_name_guessed(self):
        summary, _ = fixture()
        self.assertIsNone(self.enrich(summary, []))
        group = summary['docker_unmatched'][0]
        self.assertFalse(group['available'])
        self.assertEqual(group['status'], 'Docker host unavailable')
        self.assertEqual(group['containers'], [])

    def test_stack_only_unmatched_host_and_missing_pve(self):
        summary, servers = fixture()
        summary['pve']['guest_inventory'] = []
        summary['container_inventory'] = []
        summary['stack_problems'] = [dict(server_id=servers[0]['id'], id='orphan-stack', name='Test', host='test')]
        with patch('workload_docker.time.time', return_value=NOW):
            workload_docker.enrich(summary, servers)
        group = summary['docker_unmatched'][0]
        self.assertFalse(group['available'])
        self.assertEqual(group['status'], 'No Docker data')
        self.assertEqual(group['stack_problems'][0]['id'], 'orphan-stack')


if __name__ == '__main__':
    unittest.main()
