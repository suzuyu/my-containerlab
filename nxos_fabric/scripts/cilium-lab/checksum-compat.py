#!/usr/bin/env python3
"""Guarded, explicitly enrolled VXLAN TX checksum compatibility for kind labs.
No automatic kernel/feature selection. Runtime policy belongs outside version control.
"""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

INTERFACE = 'cilium_vxlan'
FEATURE = 'tx-checksum-ip-generic'
CONFIG_KEYS = ('routing-mode', 'tunnel-protocol', 'enable-ipv4', 'enable-ipv6',
               'bpf-lb-mode', 'enable-bpf-masquerade', 'enable-egress-gateway')


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if p.returncode:
        raise RuntimeError(f'{args[0]} {args[1:4]}: exit {p.returncode}: {p.stderr.strip()[:400]}')
    return p.stdout


def write_json(path, value):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w') as out:
        os.chmod(tmp, 0o600)
        json.dump(value, out, indent=2)
        out.write('\n')
    os.replace(tmp, path)


def kubectl(policy, *args):
    return ['kubectl', '--kubeconfig', policy['kubeconfig'], '--context', policy['context'],
            '--request-timeout=15s', *args]


def feature_value(text):
    match = re.search(r'^\s*' + FEATURE + r': (on|off)(?:\s|$)', text, re.M)
    if not match:
        raise RuntimeError('TX checksum feature unavailable')
    return match[1]


def inspect(policy):
    """Validate every target before any mutation; allow same-image Pod recreation."""
    k = lambda *a: json.loads(command(kubectl(policy, *a)))
    cluster_uid = k('get', 'namespace', 'kube-system', '-o', 'json')['metadata']['uid']
    cfg = k('-n', 'kube-system', 'get', 'configmap', 'cilium-config', '-o', 'json')['data']
    if cfg.get('routing-mode') != 'tunnel' or cfg.get('tunnel-protocol') != 'vxlan':
        raise RuntimeError('requires VXLAN tunnel mode')
    if cfg.get('enable-ipv6') != 'true':
        raise RuntimeError('requires enrolled IPv6 profile')
    agents = k('-n', 'kube-system', 'get', 'pods', '-l', 'k8s-app=cilium', '-o', 'json')['items']
    nodes = {x['metadata']['name']: x for x in k('get', 'nodes', '-o', 'json')['items']}
    result = {'cluster_uid': cluster_uid, 'host_kernel': platform.release(),
              'config': {key: cfg.get(key) for key in CONFIG_KEYS}, 'nodes': {}}
    for name in policy['nodes']:
        if name not in nodes or not any(c['type'] == 'Ready' and c['status'] == 'True'
                                       for c in nodes[name]['status']['conditions']):
            raise RuntimeError(f'{name}: Node is not Ready')
        container = json.loads(command(['docker', 'inspect', name]))[0]
        labels = container['Config'].get('Labels') or {}
        if labels.get('io.x-k8s.kind.cluster') != policy['cluster']:
            raise RuntimeError(f'{name}: wrong kind cluster')
        if labels.get('io.x-k8s.kind.role') != 'worker' or not container['State']['Running']:
            raise RuntimeError(f'{name}: not a running kind worker')
        matched = [p for p in agents if p['spec']['nodeName'] == name and not p['metadata'].get('deletionTimestamp')]
        if len(matched) != 1:
            raise RuntimeError(f'{name}: expected one active Cilium Pod')
        pod = matched[0]
        status = [s for s in pod['status'].get('containerStatuses', []) if s['name'] == 'cilium-agent']
        if len(status) != 1 or not status[0]['ready'] or not status[0].get('state', {}).get('running'):
            raise RuntimeError(f'{name}: Cilium is not Ready')
        kernel = command(['docker', 'exec', container['Id'], 'uname', '-r']).strip()
        if kernel != result['host_kernel']:
            raise RuntimeError(f'{name}: host/Node kernel mismatch')
        link = json.loads(command(['docker', 'exec', container['Id'], 'ip', '-d', '-j', 'link', 'show', INTERFACE]))[0]
        if link.get('linkinfo', {}).get('info_kind') != 'vxlan':
            raise RuntimeError(f'{name}: target interface is not VXLAN')
        features = command(['docker', 'exec', container['Id'], 'ethtool', '-k', INTERFACE])
        result['nodes'][name] = {
            'container_id': container['Id'], 'node_uid': nodes[name]['metadata']['uid'],
            'node_image': container['Image'], 'kernel': kernel,
            'cilium_image_id': status[0]['imageID'], 'cilium_pod_uid': pod['metadata']['uid'],
            'ifindex': link['ifindex'], 'tx': feature_value(features), 'features': features}
    return result


def fingerprint(observation):
    return {**{key: observation[key] for key in ('cluster_uid', 'host_kernel', 'config')},
            'nodes': {n: {key: v[key] for key in ('node_image', 'kernel', 'cilium_image_id')}
                      for n, v in observation['nodes'].items()}}


def guard(policy, observation):
    if fingerprint(observation) != policy['expected']:
        raise RuntimeError('fingerprint changed: re-evaluate kernel/image/cluster/config; no automatic apply')


def change(name, node, desired):
    # Address exact container ID, and recheck interface generation immediately before mutation.
    link = json.loads(command(['docker', 'exec', node['container_id'], 'ip', '-d', '-j', 'link', 'show', INTERFACE]))[0]
    if link['ifindex'] != node['ifindex'] or link.get('linkinfo', {}).get('info_kind') != 'vxlan':
        raise RuntimeError(f'{name}: interface changed during inspection')
    command(['docker', 'exec', node['container_id'], 'ethtool', '-K', INTERFACE, FEATURE, desired])
    after = command(['docker', 'exec', node['container_id'], 'ethtool', '-k', INTERFACE])
    if feature_value(after) != desired:
        raise RuntimeError(f'{name}: read-back failed')


def execute(policy, action):
    if not policy['enabled']:
        raise RuntimeError('policy disabled; re-enrollment required')
    before = inspect(policy)
    guard(policy, before)
    desired = policy['restore_tx'] if action == 'restore' else 'off'
    changed = []
    if action == 'check':
        if any(v['tx'] != desired for v in before['nodes'].values()):
            raise RuntimeError('checksum drift detected; run reconcile')
    else:
        for name, node in before['nodes'].items():
            if node['tx'] != desired:
                change(name, node, desired)
                changed.append(name)
    after = inspect(policy) if changed else before
    guard(policy, after)
    if any(v['tx'] != desired for v in after['nodes'].values()):
        raise RuntimeError('final feature check failed')
    return {'time': now(), 'action': action, 'status': 'ok', 'changed': changed,
            'observed': after, 'note': 'interface state only; traffic acceptance is separate'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enroll', 'check', 'reconcile', 'restore'])
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--cluster')
    parser.add_argument('--context')
    parser.add_argument('--kubeconfig')
    parser.add_argument('--node', action='append')
    parser.add_argument('--restore-tx', choices=['on', 'off'])
    parser.add_argument('--reason')
    args = parser.parse_args()
    state = args.state.resolve()
    if args.action == 'enroll':
        if not all((args.cluster, args.context, args.kubeconfig, args.node, args.restore_tx, args.reason)):
            parser.error('enroll requires cluster, context, kubeconfig, node(s), restore-tx and reason')
        if any(not re.fullmatch(r'[a-z0-9][a-z0-9-]+', n) for n in [args.cluster, *args.node]):
            parser.error('invalid cluster/Node name')
        state.parent.mkdir(parents=True, exist_ok=True)
    elif not state.is_file():
        parser.error('state does not exist; explicit enrollment required')
    with state.with_suffix('.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if args.action == 'enroll':
                if state.exists():
                    raise RuntimeError('state already exists; preserve it and use a new enrollment path')
                policy = {'schema': 1, 'enabled': True, 'cluster': args.cluster, 'context': args.context,
                          'kubeconfig': str(Path(args.kubeconfig).resolve()), 'nodes': sorted(set(args.node)),
                          'restore_tx': args.restore_tx, 'reason': args.reason, 'created': now()}
                observed = inspect(policy)
                policy['expected'] = fingerprint(observed)
                policy['enrollment_observed'] = observed
                write_json(state, policy)
                result = {'time': now(), 'action': 'enroll', 'status': 'ok', 'changed': [], 'observed': observed}
            else:
                policy = json.loads(state.read_text())
                result = execute(policy, args.action)
                if args.action == 'restore':
                    policy['enabled'] = False
                    policy['restored'] = now()
                    write_json(state, policy)
            write_json(state.with_suffix('.status.json'), result)
            print(json.dumps({key: value for key, value in result.items() if key != 'observed'}))
            return 0
        except (RuntimeError, KeyError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            result = {'time': now(), 'action': args.action, 'status': 'blocked', 'error': str(exc)}
            write_json(state.with_suffix('.status.json'), result)
            print(json.dumps(result), file=sys.stderr)
            return 1


if __name__ == '__main__':
    sys.exit(main())
