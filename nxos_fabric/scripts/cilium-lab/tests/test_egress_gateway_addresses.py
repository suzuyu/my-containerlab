"""Offline safety tests: a stateful Docker stand-in, never a live lab."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'configure-egress-gateway-addresses.sh'
MOCK = r'''#!/usr/bin/env python3
import ipaddress,json,os,pathlib,sys
p=pathlib.Path(os.environ['EGRESS_TEST_STATE']);s=json.loads(p.read_text());a=sys.argv[1:]
def save(): p.write_text(json.dumps(s))
def mutate(): s['mutations'].append(a);save()
if a[0]=='ps': print('\n'.join(s['nodes']));sys.exit()
if a[0]=='inspect': print('{}');sys.exit(0 if a[1] in s['nodes'] else 1)
assert a[0]=='exec' and a[2]=='ip', a
node=a[1];a=a[3:];d=s['nodes'][node]
if a==['-j','addr','show']:
 print(json.dumps([{'ifname':k,'addr_info':v['addresses']} for k,v in d.items()]));sys.exit()
if a==['-j','-d','link','show']:
 print(json.dumps([{'ifname':k,**v['link']} for k,v in d.items()]));sys.exit()
if a[:3]==['link','show','dev']: sys.exit(0 if a[3] in d else 1)
if a[:2]==['link','add']:
 assert a[2] not in d
 d[a[2]]={'addresses':[],'link':{'linkinfo':{'info_kind':'dummy'},'flags':[],'operstate':'UNKNOWN'}};mutate();sys.exit()
if a[:3]==['link','set','dev']:
 if a[4]=='alias':d[a[3]]['link']['ifalias']=a[5]
 elif a[4]=='up': d[a[3]]['link']['flags']=['UP']
 else:raise AssertionError(a)
 mutate();sys.exit()
if a[:3]==['link','delete','dev']: del d[a[3]];mutate();sys.exit()
if a[0] in ['-4','-6'] and a[1:3]==['addr','add']:
 x=ipaddress.ip_interface(a[3]);d[a[5]]['addresses'].append({'local':str(x.ip),'prefixlen':x.network.prefixlen});mutate();sys.exit()
raise AssertionError(a)
'''


def record(address, **kwargs):
    a = ipaddress.ip_interface(address)
    return {'local': str(a.ip), 'prefixlen': a.network.prefixlen, **kwargs}


class AddressSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.statefile = self.directory / 'state.json'
        docker = self.directory / 'docker'
        docker.write_text(MOCK)
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.directory) + ':' + os.environ['PATH'], EGRESS_TEST_STATE=str(self.statefile))
        self.initialize('adc-k02')

    def initialize(self, cluster):
        segment = 4 if cluster == 'adc-k02' else 5
        ifaces = ['bond0.14', 'bond0.104'] if segment == 4 else ['bond0.105', 'bond0.105']
        self.cluster = cluster
        nodes = {}
        for i, suffix in enumerate(['worker', 'worker2']):
            nodes[cluster + '-' + suffix] = {ifaces[i]: {'addresses': [record(f'172.16.{segment}.{21+i}/24')], 'link': {'flags': ['UP']}}}
        nodes[cluster + '-control-plane'] = {'eth0': {'addresses': [record('172.18.0.3/16')], 'link': {'flags': ['UP']}}}
        self.write({'nodes': nodes, 'mutations': []})

    def read(self):
        return json.loads(self.statefile.read_text())

    def write(self, data):
        self.statefile.write_text(json.dumps(data))

    def execute(self, action, success=True):
        p = subprocess.run(['bash', str(SCRIPT), '--cluster', self.cluster, '--action', action], env=self.env, text=True, capture_output=True, timeout=30)
        if success:
            self.assertEqual(p.returncode, 0, p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout)
        return p

    def reject_without_mutation(self, action='apply'):
        before = self.read()
        self.execute(action, success=False)
        self.assertEqual(before, self.read())

    def test_apply_repeat_check_remove_both_clusters(self):
        for cluster in ['adc-k02', 'bdc-k03']:
            with self.subTest(cluster=cluster):
                self.initialize(cluster)
                original = self.read()['nodes']
                self.execute('apply')
                s = self.read()
                for node in [cluster + '-worker', cluster + '-worker2']:
                    addresses = s['nodes'][node]['egress0']['addresses']
                    self.assertEqual({x['prefixlen'] for x in addresses}, {32, 128})
                self.execute('apply')
                self.execute('check')
                self.assertEqual(s['nodes'], self.read()['nodes'])
                self.execute('remove')
                self.assertEqual(original, self.read()['nodes'])
                self.execute('remove')

    def test_check_missing_is_readonly(self):
        self.reject_without_mutation('check')

    def test_second_node_primary_missing_prevents_first_node_changes(self):
        s = self.read(); s['nodes']['adc-k02-worker2']['bond0.104']['addresses'] = []; self.write(s)
        self.reject_without_mutation()

    def test_foreign_interface_on_second_node(self):
        s = self.read(); s['nodes']['adc-k02-worker2']['egress0'] = {'addresses': [], 'link': {'linkinfo': {'info_kind': 'dummy'}, 'ifalias': 'other'}}; self.write(s)
        self.reject_without_mutation()

    def test_duplicate_on_control_plane(self):
        s = self.read(); s['nodes']['adc-k02-control-plane']['eth0']['addresses'].append(record('172.16.24.1/32')); self.write(s)
        self.reject_without_mutation()

    def test_wrong_prefix(self):
        self.execute('apply'); s = self.read(); s['nodes']['adc-k02-worker']['egress0']['addresses'][0]['prefixlen'] = 24; self.write(s)
        self.reject_without_mutation()

    def test_ipv6_other_spelling_is_idempotent(self):
        self.execute('apply'); s = self.read()
        for a in s['nodes']['adc-k02-worker']['egress0']['addresses']:
            if ':' in a['local']: a['local'] = 'fd21:0000:0000:0024:0000:0000:0000:0001'
        self.write(s); self.execute('check'); self.execute('apply')
        self.assertEqual(s['nodes'], self.read()['nodes'])

    def test_remove_rejects_unexpected_global_address(self):
        self.execute('apply'); s = self.read(); s['nodes']['adc-k02-worker2']['egress0']['addresses'].append(record('192.0.2.50/32')); self.write(s)
        self.reject_without_mutation('remove')

    def test_wrong_link_type(self):
        self.execute('apply'); s = self.read(); s['nodes']['adc-k02-worker']['egress0']['link']['linkinfo']['info_kind'] = 'bridge'; self.write(s)
        self.reject_without_mutation('remove')

    def test_dad_failed_not_ready(self):
        self.execute('apply'); s = self.read(); s['nodes']['adc-k02-worker']['egress0']['addresses'][1]['dadfailed'] = True; self.write(s)
        p = self.execute('check', success=False)
        self.assertIn('DAD failed', p.stderr)
        self.assertEqual(s, self.read())


if __name__ == '__main__':
    unittest.main()
