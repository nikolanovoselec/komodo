import unittest
import adapter

class Filtering(unittest.TestCase):
    def test_disabled_is_explicit_not_a_failed_state(self):
        servers = [{'id':'on','info':{'state':'NotOk'}}, {'id':'off','info':{'state':'Disabled'}}]
        tags = [{'_id':{'$oid':'d'},'name':'disabled'}]
        stacks = [dict(id=n,name=n,tags=t,info={'server_id':h,'state':state}) for n,t,h,state in [('failed',[],'on','down'),('hidden',['d'],'on','stopped'),('offline',[],'off','unknown'),('unassigned',[],'','unknown')]]
        visible = adapter.visible_stacks(servers, stacks, tags)
        self.assertEqual([x['name'] for x in visible], ['failed','unassigned'])

    def test_projection_hides_exact_disabled_members_not_prefixes(self):
        servers = [{'id':'on','info':{'state':'Ok'}}]
        stacks = [dict(id=n,name=n,tags=t,info={'server_id':'on','server_name':'host','state':state}) for n,t,state in [('app',['d'],'stopped'),('web',[],'running')]]
        containers = [dict(name=n,server_id='on',server_name='host',state=state,status=status,stats={'cpu_perc':cpu,'mem_usage':mem}) for n,state,status,cpu,mem in [('app-db','exited','Exited','0%','1MiB / 2GiB'),('app-other','exited','Exited','0%','1MiB / 2GiB'),('web','running','Up (unhealthy)','2.5%','2GiB / 4GiB'),('busy','running','Up','12.0%','400MiB / 4GiB')]]
        result = adapter.project(servers, stacks, [{'_id':{'$oid':'d'},'name':'disabled'}], containers, {('on','app-db')})
        self.assertEqual(result['containers_total'], 3)
        self.assertEqual({x['name'] for x in result['container_problems']}, {'app-other','web'})
        self.assertEqual(result['top_cpu'][0]['name'], 'busy')
        self.assertEqual(result['top_ram'][0]['name'], 'web')
        self.assertEqual(result['running_stacks'], 1)

    def test_collect_uses_deployed_membership_and_does_not_return_secrets(self):
        calls = []
        def api(kind, params):
            calls.append((kind,params))
            return {'ListServers':[{'id':'on','info':{'state':'Ok'}}],
                    'ListTags':[{'_id':{'$oid':'d'},'name':'disabled'}],
                    'ListStacks':[{'id':'disabled','name':'old','tags':['d'],'info':{'server_id':'on'}}],
                    'ListAllDockerContainers':[],
                    'GetStack':{'info':{'deployed_services':[{'container_name':'exact'}]},'config':{'secret':'do-not-expose'}}}[kind]
        result = adapter.collect(api)
        self.assertEqual(result['containers_total'],0)
        self.assertNotIn('do-not-expose',str(result))
        self.assertIn(('GetStack',{'stack':'disabled'}),calls)
        self.assertIn(('ListAllDockerContainers',{'limit':0}),calls)

    def test_http_failure_is_explicit_and_sanitized(self):
        import threading, urllib.request, urllib.error, json
        server = adapter.make_server(('127.0.0.1',0), lambda: (_ for _ in ()).throw(RuntimeError('secret-token')))
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen('http://127.0.0.1:%s/summary' % server.server_port)
            self.assertEqual(raised.exception.code,503)
            self.assertNotIn('secret-token',raised.exception.read().decode())
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
