"""Exercise the convergence driver against isolated fake tools, never a cluster."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

DRIVER = Path(__file__).resolve().parents[1] / 'converge-cilium-lab.sh'
STUB = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as f:
    f.write(json.dumps([name, *args]) + '\\n')
if name == 'kubectl':
    if args[:2] == ['config', 'get-contexts']:
        print('kind-adc-k02\\nkind-bdc-k03')
    elif 'namespace' in args:
        context = args[args.index('--context') + 1]
        uid = os.environ.get('UID_K03', 'uid-k03') if context == 'kind-bdc-k03' else 'uid-k02'
        if '--kubeconfig' in args and os.environ.get('BAD_STATE_KUBECONFIG'):
            uid = 'other-cluster'
        print(uid)
if name == 'checksum-compat.py' and args[0] == 'reconcile':
    if os.environ.get('FAIL_RECONCILE') and args[-1].endswith('k03.json'):
        sys.exit(9)
'''


class ConvergeChecksum(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scripts = self.root / 'nxos_fabric/scripts/cilium-lab'
        self.scripts.mkdir(parents=True)
        self.driver = self.scripts / DRIVER.name
        shutil.copyfile(DRIVER, self.driver)
        for name in ['render-cilium-lab.sh', 'configure-cilium-node-labels.sh',
                     'preflight-host-and-kind.sh', 'render-k8s-api-values.sh',
                     'configure-coredns-upstream.sh', 'configure-bgp-aggregate-blackhole.sh',
                     'prepare-clustermesh-shared-ca.sh', 'checksum-compat.py']:
            p = self.scripts / name
            p.write_text(STUB)
            p.chmod(0o755)
        (self.scripts / 'configure-egress-interface-init.sh').write_text('#!/bin/bash\nexit 0\n')
        for site in ['singlesite', 'multisite']:
            client = self.root / f'nxos_fabric/nxos_{site}/k8s_kind/client'
            (client / 'runtime/bin').mkdir(parents=True)
            (client / 'runtime/charts').mkdir()
            (client / 'chart-versions.env').write_text('CILIUM_CHART_VERSION=1\nTETRAGON_CHART_VERSION=1\n')
            for chart in ['cilium', 'tetragon']:
                (client / f'runtime/charts/{chart}-1.tgz').touch()
            for tool in ['kubectl', 'helm', 'cilium', 'docker']:
                p = client / f'runtime/bin/{tool}'
                p.write_text(STUB)
                p.chmod(0o755)
        self.log = self.root / 'calls.jsonl'
        self.env = dict(os.environ, CALLS=str(self.log))
        self.states = {}
        for site, cluster in [('k02', 'adc-k02'), ('k03', 'bdc-k03')]:
            p = self.root / f'{site}.json'
            p.write_text(json.dumps({'schema': 1, 'enabled': True, 'cluster': cluster,
                                    'context': 'kind-' + cluster,
                                    'nodes': [cluster + '-worker', cluster + '-worker2'],
                                    'kubeconfig': str(self.root / f'{site}.conf'),
                                    'expected': {'cluster_uid': 'uid-' + site}}))
            self.states[site] = p

    def run_driver(self, profile='multisite-final', apply=True, sites=('k02', 'k03')):
        args = ['bash', str(self.driver), '--profile', profile]
        for site in sites:
            args += ['--checksum-state-' + site, str(self.states[site])]
        if apply:
            args += ['--apply']
        result = subprocess.run(args, env=self.env, text=True, capture_output=True, timeout=20)
        self.calls = [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
        return result

    def writes(self):
        return [c for c in self.calls if (c[0] == 'helm' and 'upgrade' in c)
                or c[0] == 'configure-cilium-node-labels.sh']

    def test_multisite_reconciles_each_cluster_before_its_dns(self):
        result = self.run_driver()
        self.assertEqual(result.returncode, 0, result.stderr)
        for site, context in [('k02', 'kind-adc-k02'), ('k03', 'kind-bdc-k03')]:
            reconcile = self.calls.index(['checksum-compat.py', 'reconcile', '--state', str(self.states[site])])
            check = self.calls.index(['checksum-compat.py', 'check', '--state', str(self.states[site])])
            dns = next(i for i, c in enumerate(self.calls) if c[0] == 'configure-coredns-upstream.sh' and context in c)
            install = next(i for i, c in enumerate(self.calls) if c[0] == 'helm' and 'cilium' in c and context in c)
            self.assertLess(install, reconcile)
            self.assertLess(reconcile, check)
            self.assertLess(check, dns)
        first_write = self.calls.index(self.writes()[0])
        for context in ['kind-adc-k02', 'kind-bdc-k03']:
            self.assertTrue(any(c[0] == 'kubectl' and '--kubeconfig' in c and context in c for c in self.calls[:first_write]))

    def test_wrong_second_cluster_uid_stops_before_first_cluster_write(self):
        self.env['UID_K03'] = 'new-k03'
        result = self.run_driver()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('another cluster UID', result.stderr)
        self.assertEqual(self.writes(), [])

    def test_state_kubeconfig_must_match_selected_cluster(self):
        self.env['BAD_STATE_KUBECONFIG'] = '1'
        result = self.run_driver()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('kubeconfig points to another cluster UID', result.stderr)
        self.assertEqual(self.writes(), [])

    def test_swapped_state_and_wrong_workers_are_rejected(self):
        p = self.states['k03']
        policy = json.loads(p.read_text())
        for change in [{'cluster': 'adc-k02'}, {'nodes': ['bdc-k03-control-plane']}]:
            with self.subTest(change=change):
                p.write_text(json.dumps({**policy, **change}))
                result = self.run_driver()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls, [])

    def test_reconcile_failure_prevents_second_dns_and_later_components(self):
        self.env['FAIL_RECONCILE'] = '1'
        result = self.run_driver()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] == 'configure-coredns-upstream.sh' and 'kind-bdc-k03' in c for c in self.calls))
        self.assertFalse(any(c[0] == 'helm' and 'tetragon' in c for c in self.calls))

    def test_offline_render_does_not_connect_or_apply(self):
        result = self.run_driver(apply=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c[0] for c in self.calls], ['render-cilium-lab.sh'])

    def test_singlesite_existing_option_still_works(self):
        result = self.run_driver(profile='singlesite-final', sites=('k02',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['checksum-compat.py', 'check', '--state', str(self.states['k02'])], self.calls)

    def test_k03_state_rejected_for_singlesite(self):
        result = self.run_driver(profile='singlesite-final')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
