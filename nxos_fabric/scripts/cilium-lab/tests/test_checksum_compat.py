import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
compat = module('checksum-compat')
probe = module('probe-ipv6-checksum')

class Guards(unittest.TestCase):
    def setUp(self):
        self.obs = {'cluster_uid': 'cluster-one', 'host_kernel': 'kernel-one', 'config': {'routing-mode': 'tunnel'},
                    'nodes': {'worker': {'node_image': 'digest-one', 'kernel': 'kernel-one', 'cilium_image_id': 'cilium-one', 'tx': 'off', 'ifindex': 4, 'container_id': 'first'}}}
        self.policy = {'enabled': True, 'expected': compat.fingerprint(self.obs), 'restore_tx': 'on'}

    def test_updated_kernel_cannot_apply(self):
        self.obs['host_kernel'] = 'kernel-two'
        with patch.object(compat, 'inspect', return_value=self.obs), patch.object(compat, 'change') as change:
            with self.assertRaisesRegex(RuntimeError, 'fingerprint changed'):
                compat.execute(self.policy, 'reconcile')
            change.assert_not_called()

    def test_updated_cluster_or_image_cannot_apply(self):
        for key in ('cluster_uid', 'node_image', 'cilium_image_id'):
            obs = copy.deepcopy(self.obs)
            if key == 'cluster_uid': obs[key] = 'new'
            else: obs['nodes']['worker'][key] = 'new'
            with self.subTest(key=key), patch.object(compat, 'inspect', return_value=obs), patch.object(compat, 'change') as change:
                with self.assertRaises(RuntimeError): compat.execute(self.policy, 'reconcile')
                change.assert_not_called()

    def test_same_image_recreated_interface_is_repaired(self):
        before = copy.deepcopy(self.obs)
        before['nodes']['worker'].update(tx='on', ifindex=9, container_id='replacement')
        after = copy.deepcopy(before)
        after['nodes']['worker']['tx'] = 'off'
        with patch.object(compat, 'inspect', side_effect=[before, after]), patch.object(compat, 'change') as change:
            result = compat.execute(self.policy, 'reconcile')
            self.assertEqual(result['changed'], ['worker'])
            change.assert_called_once_with('worker', before['nodes']['worker'], 'off')

    def test_check_detects_drift_without_mutation(self):
        self.obs['nodes']['worker']['tx'] = 'on'
        with patch.object(compat, 'inspect', return_value=self.obs), patch.object(compat, 'change') as change:
            with self.assertRaisesRegex(RuntimeError, 'drift'): compat.execute(self.policy, 'check')
            change.assert_not_called()

    def test_noop_does_not_write_interface(self):
        with patch.object(compat, 'inspect', return_value=self.obs), patch.object(compat, 'change') as change:
            self.assertEqual(compat.execute(self.policy, 'reconcile')['changed'], [])
            change.assert_not_called()

    def test_unready_inspection_does_not_apply(self):
        with patch.object(compat, 'inspect', side_effect=RuntimeError('Cilium is not Ready')), patch.object(compat, 'change') as change:
            with self.assertRaises(RuntimeError): compat.execute(self.policy, 'reconcile')
            change.assert_not_called()

    def test_failed_readback_is_not_success(self):
        self.obs['nodes']['worker']['tx'] = 'on'
        with patch.object(compat, 'inspect', return_value=self.obs), patch.object(compat, 'change'):
            with self.assertRaisesRegex(RuntimeError, 'final feature'): compat.execute(self.policy, 'reconcile')

    def test_disabled_cannot_reapply(self):
        self.policy['enabled'] = False
        with patch.object(compat, 'inspect') as inspect:
            with self.assertRaisesRegex(RuntimeError, 'disabled'): compat.execute(self.policy, 'reconcile')
            inspect.assert_not_called()

    def test_probe_negative_is_not_permission_failure(self):
        rows = [{'flags': f, 'test_errno': 0, 'helper_return': 0 if f != 144 else -22} for f in (0,16,144)]
        self.assertEqual(probe.classify(rows), 'unsupported')
        rows[2]['test_errno'] = 1
        self.assertEqual(probe.classify(rows), 'unknown')
        rows[2].update(test_errno=0, helper_return=0)
        self.assertEqual(probe.classify(rows), 'supported')
        rows[0]['helper_return'] = -22
        self.assertEqual(probe.classify(rows), 'unknown')

if __name__ == '__main__': unittest.main()
