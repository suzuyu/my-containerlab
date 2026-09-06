#!/usr/bin/env python3
"""Install a guarded per-user systemd timer for one enrolled checksum policy.
Linger is an explicit, separate user-level setting; see the operations guide.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', required=True, type=Path)
    p.add_argument('--runtime-bin', required=True, type=Path)
    p.add_argument('--unit', required=True)
    a = p.parse_args()
    state, runtime = a.state.resolve(), a.runtime_bin.resolve()
    script = Path(__file__).resolve().with_name('checksum-compat.py')
    if not re.fullmatch(r'cilium-checksum-[a-z0-9-]+', a.unit):
        p.error('unit must start with cilium-checksum- and contain lowercase letters/digits/hyphens')
    if any(not re.fullmatch(r'[A-Za-z0-9_./-]+', str(x)) for x in (state, runtime, script)):
        p.error('unit paths must use letters/digits, underscore, slash, dot or hyphen')
    if not json.loads(state.read_text())['enabled']:
        p.error('policy must be enrolled and enabled')
    env = dict(os.environ, PATH=f'{runtime}:/usr/local/bin:/usr/bin:/bin')
    subprocess.run(['/usr/bin/python3', str(script), 'check', '--state', str(state)], env=env, check=True, stdout=subprocess.DEVNULL)
    directory = Path.home() / '.config/systemd/user'
    directory.mkdir(parents=True, exist_ok=True)
    units = {
        '.service': f'''# Managed by install-checksum-monitor.py for {state}
[Unit]
Description=Guarded Cilium VXLAN checksum compatibility ({a.unit})
[Service]
Type=oneshot
Environment=PATH={runtime}:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 {script} reconcile --state {state}
TimeoutStartSec=90
UMask=0077
''',
        '.timer': f'''# Managed by install-checksum-monitor.py for {state}
[Unit]
Description=Check enrolled Cilium checksum compatibility every 30 seconds
[Timer]
OnBootSec=30s
OnUnitInactiveSec=30s
AccuracySec=1s
Unit={a.unit}.service
[Install]
WantedBy=timers.target
'''}
    # Reject collisions before writing either file.
    for suffix, content in units.items():
        f = directory / (a.unit + suffix)
        if f.exists() and f.read_text() != content:
            p.error(f'existing different unit: {f}; review it before replacement')
    for suffix, content in units.items():
        (directory / (a.unit + suffix)).write_text(content)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', a.unit + '.timer'], check=True)
    subprocess.run(['systemctl', '--user', 'start', a.unit + '.service'], check=True)
    subprocess.run(['systemctl', '--user', 'is-active', a.unit + '.timer'], check=True)
    print('Installed. Inspect journalctl --user -u ' + a.unit + '.service and the policy .status.json.')
    subprocess.run(['loginctl', 'show-user', str(os.getuid()), '-p', 'Linger'], check=True)


if __name__ == '__main__':
    main()
