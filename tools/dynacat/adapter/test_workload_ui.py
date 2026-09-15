import unittest
from pathlib import Path
from workload_docker import exception_visibility

class WorkloadUI(unittest.TestCase):
    def test_exception_visibility_combinations(self):
        for unmatched,definitions,expected in [([],[],(False,False,False)),([{}],[],(True,True,False)),([],[{}],(True,False,True)),([{}],[{}],(True,True,True))]:
            with self.subTest(unmatched=unmatched,definitions=definitions):
                d=exception_visibility(unmatched,definitions)
                self.assertEqual((d['show_any'],d['show_unmatched'],d['show_definitions']),expected)
                self.assertFalse(d['error'])
    def test_unavailable_not_successful_zero(self):
        for a,b in [(None,[]),([],None),(None,None)]:
            self.assertTrue(exception_visibility(a,b)['error'])
    def test_no_per_machine_docker_aggregate_metrics(self):
        config=(Path(__file__).resolve().parents[1]/'config/dynacat.yml').read_text()
        workload=config.split('      title: Workloads\n',1)[1].split('    - type:',1)[0]
        self.assertNotIn('cw-docker-stats',workload)
        self.assertIn('cw-container',workload)
        self.assertIn('CPU: Proxmox;',workload)
        self.assertIn('update-interval: 1s',workload)
    def test_status_color_and_control_contract(self):
        config=(Path(__file__).resolve().parents[1]/'config/dynacat.yml').read_text()
        self.assertIn('data-cw-collapse',config)
        self.assertIn('aria-controls="cw-containers-',config)
        self.assertIn('docker_exceptions.show_any',config)
        self.assertIn('docker_exceptions.show_unmatched',config)
        self.assertIn('docker_exceptions.show_definitions',config)
        self.assertIn('docker_exceptions.error',config)
        self.assertNotIn('METRIC SOURCES',config)
        self.assertIn('{{ if gt (len (.JSON.Array "container_problems")) 0 }}cw-issue{{ else }}cw-normal{{ end }}',config)
        self.assertIn('{{ if gt (len (.JSON.Array "stack_problems")) 0 }}cw-issue{{ else }}cw-normal{{ end }}',config)
if __name__=='__main__':unittest.main()
