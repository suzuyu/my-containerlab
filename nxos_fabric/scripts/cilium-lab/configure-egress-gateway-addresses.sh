#!/usr/bin/env bash
set -euo pipefail
# The controller runs on the lab host; no Python dependency is added to Kind nodes.
exec python3 - "$@" <<'PY'
import argparse
import ipaddress
import json
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description='Manage dedicated routed Egress /32 and /128 addresses on an owned dummy interface. No BGP or Policy changes.')
parser.add_argument('--cluster', required=True, choices=['adc-k02', 'bdc-k03'])
parser.add_argument('--action', required=True, choices=['check', 'apply', 'remove'])
args = parser.parse_args()
iface = 'egress0'
owner = 'cilium-lab-egress:' + args.cluster
site = 24 if args.cluster == 'adc-k02' else 25
node_segment = 4 if site == 24 else 5
nodes = [args.cluster + '-worker', args.cluster + '-worker2']
fabric = ['bond0.14', 'bond0.104'] if site == 24 else ['bond0.105', 'bond0.105']
expected = {node: [f'172.16.{site}.{i}/32', f'fd21:0:0:{site}::{i}/128'] for i, node in enumerate(nodes, 1)}

def fail(message):
    raise RuntimeError(message)

def run(*cmd):
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        fail(' '.join(cmd) + ': ' + p.stderr.strip())
    return p.stdout

def ip(node, *cmd):
    return run('docker', 'exec', node, 'ip', *cmd)

def addresses(node):
    return json.loads(ip(node, '-j', 'addr', 'show'))

def normalized(record):
    return ipaddress.ip_interface(f"{record['local']}/{record['prefixlen']}")

def link(node):
    links = json.loads(ip(node, '-j', '-d', 'link', 'show'))
    return next((x for x in links if x['ifname'] == iface), None)

def verify_owned(node, obj):
    if obj.get('linkinfo', {}).get('info_kind') != 'dummy' or obj.get('ifalias') != owner:
        fail(f'{node}: {iface} exists but is not an owned dummy interface; leave it unchanged')
    allowed = {ipaddress.ip_interface(x) for x in expected[node]}
    for dev in addresses(node):
        if dev['ifname'] != iface:
            continue
        for rec in dev.get('addr_info', []):
            addr = normalized(rec)
            if addr not in allowed and not addr.ip.is_link_local:
                fail(f'{node}: unexpected address {addr} on {iface}; leave it unchanged')

def ready(node):
    required = {ipaddress.ip_interface(x) for x in expected[node]}
    for _ in range(10):
        found = set()
        for dev in addresses(node):
            if dev['ifname'] != iface:
                continue
            for rec in dev.get('addr_info', []):
                addr = normalized(rec)
                if addr not in required:
                    continue
                flags = rec.get('flags', [])
                if rec.get('dadfailed') or 'dadfailed' in flags:
                    fail(f'{node}: DAD failed for {addr}')
                if not rec.get('tentative') and 'tentative' not in flags:
                    found.add(addr)
        obj = link(node)
        if obj and 'UP' in obj.get('flags', []) and obj.get('operstate', '').upper() in ('UP', 'UNKNOWN') and found == required:
            return
        time.sleep(1)
    fail(f'{node}: addresses or {iface} are not ready')

try:
    # Complete preflight on both nodes before modifying either node.
    target_ips = {ipaddress.ip_interface(x).ip: n for n, values in expected.items() for x in values}
    for idx, node in enumerate(nodes):
        run('docker', 'inspect', node)
        ip(node, 'link', 'show', 'dev', fabric[idx])
        primary = ipaddress.ip_interface(f'172.16.{node_segment}.{21+idx}/24')
        current = addresses(node)
        if not any(d['ifname'] == fabric[idx] and any(normalized(a) == primary for a in d.get('addr_info', [])) for d in current):
            fail(f'{node}: expected Fabric primary address {primary} missing')
        obj = link(node)
        if obj:
            verify_owned(node, obj)
        elif args.action == 'check':
            fail(f'{node}: {iface} is absent')
    # Detect duplicates on all running Kind nodes for this cluster, including control-plane.
    for node in run('docker', 'ps', '--format', '{{.Names}}').splitlines():
        if not node.startswith(args.cluster + '-'):
            continue
        for dev in addresses(node):
            for rec in dev.get('addr_info', []):
                addr = normalized(rec)
                if addr.ip in target_ips:
                    intended = target_ips[addr.ip]
                    if node != intended or dev['ifname'] != iface or addr not in {ipaddress.ip_interface(x) for x in expected[intended]}:
                        fail(f'duplicate/wrong prefix: {addr} on {node}/{dev["ifname"]}')
    for node in nodes:
        obj = link(node)
        if args.action == 'apply':
            if not obj:
                ip(node, 'link', 'add', iface, 'type', 'dummy')
                ip(node, 'link', 'set', 'dev', iface, 'alias', owner)
            ip(node, 'link', 'set', 'dev', iface, 'up')
            have = {normalized(a) for d in addresses(node) if d['ifname'] == iface for a in d.get('addr_info', [])}
            for value in expected[node]:
                addr = ipaddress.ip_interface(value)
                if addr not in have:
                    ip(node, '-4' if addr.version == 4 else '-6', 'addr', 'add', str(addr), 'dev', iface)
        elif args.action == 'remove' and obj:
            # All unexpected global addresses and ownership were checked above.
            ip(node, 'link', 'delete', 'dev', iface)
        if args.action in ('apply', 'check'):
            ready(node)
            print(f'{node} {iface} IPv4=true IPv6=true ownership=OK', flush=True)
        else:
            if link(node):
                fail(f'{node}: {iface} still exists')
            print(f'{node} {iface} absent=true', flush=True)
except (RuntimeError, OSError, ValueError) as exc:
    print('ERROR: ' + str(exc), file=sys.stderr)
    sys.exit(1)
PY
