"""Only the verified successful one-shot job is not a stopped daemon."""
import unittest
import adapter
TOOLS='6819f646d0f8c95b939cbf2f'
class CompletedJobs(unittest.TestCase):
    def project(self,**changes) -> dict:
        c=dict(server_id=TOOLS,server_name='tools',name='tools_dynacat_geoip_update',state='exited',status='Exited (0) About a minute ago');c.update(changes)
        return adapter.project([{'id':TOOLS,'name':'tools','info':{'state':'Ok'}}],[],[],[c],set())
    def test_success_is_reported_separately_not_as_failed_daemon(self):
        d=self.project()
        self.assertEqual(d['container_problems'],[])
        self.assertEqual(d['containers_total'],0)
        self.assertEqual(d['completed_jobs'][0]['name'],'tools_dynacat_geoip_update')
    def test_failure_or_wrong_identity_is_never_suppressed(self):
        for changes in [{'status':'Exited (1) now'},{'status':''},{'name':'another-job'},{'server_id':'other'}]:
            with self.subTest(changes=changes):self.assertEqual(len(self.project(**changes)['container_problems']),1)
    def test_running_job_remains_a_running_container(self):
        d=self.project(state='running',status='Up 1 second')
        self.assertEqual(d['running_containers'],1)
if __name__=='__main__':unittest.main()
