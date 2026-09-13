"""Run the embedded address readiness predicate against iproute2 JSON forms."""
import json
import os
from pathlib import Path
import subprocess
import unittest

MANIFEST = (Path(__file__).resolve().parents[3] / 'nxos_singlesite/k8s_kind/k02/'
            'cilium/manifests/egress-interface-init/daemonset.yaml')


class AddressReadiness(unittest.TestCase):
    def test_iproute2_dad_formats(self):
        text = MANIFEST.read_text()
        start = text.index('                address_ready() {')
        end = text.index('                desired_contains() {', start)
        function = '\n'.join(line[16:] for line in text[start:end].splitlines())
        cases = [({}, True), ({'tentative': True}, False), ({'dadfailed': True}, False),
                 ({'flags': ['tentative']}, False), ({'flags': ['dadfailed']}, False),
                 ({'flags': ['permanent'], 'tentative': False}, True)]
        for extra, ready in cases:
            with self.subTest(extra=extra):
                record = {'local': 'fd21:0:0:24::1', 'prefixlen': 128, **extra}
                env = dict(os.environ, EGRESS_TEST_IP_JSON=json.dumps([{'addr_info': [record]}]))
                script = ('INTERFACE=egress0\n'
                          'ip() { printf "%s" "$EGRESS_TEST_IP_JSON"; }\n' + function +
                          '\naddress_ready 6 fd21:0:0:24::1/128\n')
                p = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode == 0, ready, p.stderr)


if __name__ == '__main__':
    unittest.main()
