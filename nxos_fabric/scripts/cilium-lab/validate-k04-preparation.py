#!/usr/bin/env python3
"""Offline acceptance checks for the k04 preparation bundle.

Uses the cached Helm binary's YAML parser, so no extra Python packages, cluster
API, Docker socket, or downloads are needed. Run the preparation renderer first.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[3]
LAB = REPO / 'nxos_fabric/nxos_multisite'
K04 = LAB / 'k8s_kind/k04'
HELM = LAB / 'k8s_kind/client/runtime/bin/helm'


def read_yaml(paths):
    """Decode multiple YAML documents offline with the existing Helm runtime."""
    with tempfile.TemporaryDirectory(prefix='k04-yaml-check-') as tmp:
        chart = Path(tmp)
        (chart / 'templates').mkdir()
        (chart / 'inputs').mkdir()
        (chart / 'Chart.yaml').write_text('apiVersion: v2\nname: yaml-check\nversion: 0.1.0\n')
        index = {}
        for i, path in enumerate(paths):
            key = f'inputs/{i:03}.yaml'
            (chart / key).write_text(path.read_text())
            index[key] = path
        (chart / 'templates/read.yaml').write_text('''{{- $rows := list -}}
{{- range $path, $_ := .Files.Glob "inputs/*.yaml" -}}
  {{- $docs := list -}}
  {{- range splitList "\\n---" ($.Files.Get $path) -}}
    {{- if trim . -}}
      {{- $doc := fromYaml . -}}
      {{- if hasKey $doc "Error" -}}{{ fail (get $doc "Error") }}{{- end -}}
      {{- $docs = append $docs $doc -}}
    {{- end -}}
  {{- end -}}
  {{- $rows = append $rows (dict "path" $path "documents" $docs) -}}
{{- end }}
apiVersion: v1
kind: List
items: {{ $rows | toJson }}
''')
        out = subprocess.check_output([str(HELM), 'template', 'yaml-check', str(chart)], text=True)
        rows = json.loads(out.split('\nitems: ', 1)[1])
        return {index[x['path']]: x['documents'] for x in rows}


def require(value, message):
    if not value:
        raise SystemExit('FAIL: ' + message)


def selected(selector, service):
    labels = dict(service['metadata'].get('labels', {}))
    labels['io.kubernetes.service.name'] = service['metadata']['name']
    labels['io.kubernetes.service.namespace'] = service['metadata']['namespace']
    require(not selector.get('matchExpressions'), 'review selector expressions explicitly')
    return all(labels.get(k) == v for k, v in selector.get('matchLabels', {}).items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-dir', required=True, type=Path)
    args = parser.parse_args()
    base = LAB / 'nxos-fabric-multisite-no-cdc.clab.yaml'
    topo = LAB / 'nxos-fabric-multisite-no-cdc-k04.clab.yaml'
    kind_paths = [LAB / f'k8s_kind/{s}/{s}.kind.yaml' for s in ['k02', 'k03', 'k04']]
    rendered = [args.render_dir / n for n in ['k04-platform-resources.yaml', 'k04-handover-app-a.yaml', 'k04-validation-preflight.yaml', 'k02-cilium.yaml', 'k03-cilium.yaml', 'k04-cilium.yaml', 'k04-tetragon.yaml']]
    values_paths = [K04 / f'cilium/values/{n}' for n in ['00-base.yaml', '20-multisite-clustermesh.yaml', '90-clustermesh-three-clusters.yaml']]
    data = read_yaml([base, topo, *kind_paths, *rendered, *values_paths])
    b, t = data[base][0], data[topo][0]
    require(b['name'] == t['name'] and b['mgmt'] == t['mgmt'], 'lab name/management changed')
    require(b['topology']['kinds'] == t['topology']['kinds'], 'existing kind/image defaults changed')
    bn, tn = b['topology']['nodes'], t['topology']['nodes']
    expected_image = 'kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed'
    require(tn['adc-k04'].get('image') == expected_image, 'k04 must explicitly use the pinned Kubernetes 1.36.4 image')
    added = {'adc-k04', 'adc-k04-control-plane', 'adc-k04-worker', 'adc-k04-worker2'}
    require(set(tn) - set(bn) == added and all(tn.get(k) == v for k, v in bn.items()), 'existing nodes changed or unexpected nodes added')
    bl, tl = b['topology']['links'], t['topology']['links']
    # New links are placed in their Leaf blocks, rather than appended at EOF.
    added_links = [link for link in tl if any(ep.split(':', 1)[0] in added for ep in link['endpoints'])]
    existing_links = [link for link in tl if link not in added_links]
    require(existing_links == bl and len(added_links) == 6, 'existing links changed or wrong added-link count')
    endpoints = [ep for link in tl for ep in link['endpoints']]
    require(len(endpoints) == len(set(endpoints)), 'duplicate interface endpoint')
    require(all(ep.split(':', 1)[0] in tn for ep in endpoints), 'link references missing node')
    expected_links = set()
    for role, leaves, port in [('control-plane', ['0103', '0104'], 9), ('worker', ['0103', '0104'], 10), ('worker2', ['0101', '0102'], 9)]:
        for i, leaf in enumerate(leaves, 1):
            expected_links.add(frozenset([f'adc-lfsw{leaf}:Ethernet1/{port}', f'adc-k04-{role}:eth{i}']))
    require({frozenset(x['endpoints']) for x in added_links} == expected_links, 'Nexus design port mapping differs')
    for role, num, suffix, vlan in [('control-plane', 11, '1:1', 16), ('worker', 21, '2:1', 16), ('worker2', 22, '2:2', 106)]:
        node = tn[f'adc-k04-{role}']
        command = '\n'.join(node['exec'])
        for token in [f'VLAN_ID="{vlan}"', f'KUBELET_NODE_IP="172.16.6.{num},fd21:0:0:6::{suffix}"', 'MTU="9150"', 'sh -euc', '172.16.0.0/16 via 172.16.6.1', 'fd21:0:0::/48 via fd21:0:0:6::1']:
            require(token in command, f'{role}: missing {token}')
        init = command.index('/scripts/init-bond-singlevlan-route.sh')
        require(command.index('/cilium-lab-scripts/configure-kubelet-node-ip.sh') > init, 'Node IP set before network setup')
    nets = []
    for path in kind_paths:
        cfg = data[path][0]
        for key in ['podSubnet', 'serviceSubnet']:
            for cidr in cfg['networking'][key].split(','):
                network = ipaddress.ip_network(cidr)
                require(all(network.version != n.version or not network.overlaps(n) for n in nets), 'overlapping Pod/Service CIDRs')
                nets.append(network)
    cfg = data[kind_paths[-1]][0]
    require(all('image' not in n for n in cfg['nodes']), 'Kind node image override conflicts with topology image')
    require(cfg['networking']['disableDefaultCNI'] and cfg['networking']['kubeProxyMode'] == 'none', 'Kind CNI/kube-proxy mismatch')
    require([n['role'] for n in cfg['nodes']] == ['control-plane', 'worker', 'worker'], 'unexpected node layout')
    require(all(any(m['containerPath'] == '/cilium-lab-scripts' for m in n['extraMounts']) for n in cfg['nodes']), 'Node IP helper mount missing')
    values = data[values_paths[0]][0]
    require(values['cluster'] == {'name': 'adc-k04', 'id': 4}, 'cluster identity mismatch')
    require(values['egressGateway']['enabled'] is False and values['bpf']['masquerade'] is False, 'Egress unexpectedly enabled')
    for path in values_paths[1:]:
        peers = data[path][0]['clustermesh']['config']['clusters']
        require({x['name'] for x in peers} == {'adc-k02', 'bdc-k03', 'adc-k04'} and len(peers) == 3, 'incomplete Mesh cluster list')
    platform = data[rendered[0]]
    require(len(platform) == 7, 'unexpected resources in initial platform')
    mesh_service = next(x for x in platform if x['kind'] == 'Service')
    pool = next(x for x in platform if x['kind'] == 'CiliumLoadBalancerIPPool')
    require(selected(pool['spec']['serviceSelector'], mesh_service), 'Mesh pool does not select API')
    require({x['start'] for x in pool['spec']['blocks']} == {'172.16.34.10', 'fd21:0:0:34:0:0:1:10'} and all(x['start'] == x['stop'] for x in pool['spec']['blocks']), 'broad or wrong initial pool')
    ads = [a for x in platform if x['kind'] == 'CiliumBGPAdvertisement' for a in x['spec']['advertisements']]
    require(len(ads) == 1 and selected(ads[0]['selector'], mesh_service), 'initial advertisement must select Mesh only')
    require(ads[0]['attributes']['communities']['standard'] == ['65012:514'], 'Mesh community mismatch')
    require(set(ads[0]['service']) == {'addresses'}, 'initial aggregate advertisement present')
    bgp = next(x for x in platform if x['kind'] == 'CiliumBGPClusterConfig')['spec']['bgpInstances'][0]
    require(bgp['localASN'] == 65012 and {x['peerASN'] for x in bgp['peers']} == {65010}, 'ASN mismatch')
    require({x['peerAddress'] for x in bgp['peers']} == {'172.16.6.4', '172.16.6.5', 'fd21:0:0:6::4', 'fd21:0:0:6::5'}, 'BGR peer mismatch')
    app = data[rendered[1]]
    service = next(x for x in app if x['kind'] == 'Service')
    require(service['metadata']['labels']['handover-state'] == 'off', 'application starts advertising')
    rank_ads = [a for x in app if x['kind'] == 'CiliumBGPAdvertisement' for a in x['spec']['advertisements']]
    require(not any(selected(a['selector'], service) for a in [*ads, *rank_ads]), 'off app matches an advertisement')
    require({a['attributes']['communities']['standard'][0] for a in rank_ads} == {'65010:100', '65010:200', '65010:300'}, 'handover ranks mismatch')
    app_pool = next(x for x in app if x['kind'] == 'CiliumLoadBalancerIPPool')
    require(selected(app_pool['spec']['serviceSelector'], service) and all(x['start'] == x['stop'] for x in app_pool['spec']['blocks']), 'app pool not scoped to exact VIPs')
    require(all(set(a['service']) == {'addresses'} for a in rank_ads), 'handover aggregation is unsafe')
    for state, rank in [('candidate', 100), ('current', 200), ('preferred', 300)]:
        trial = json.loads(json.dumps(service))
        trial['metadata']['labels']['handover-state'] = state
        matches = [ad for ad in [*ads, *rank_ads] if selected(ad['selector'], trial)]
        require(len(matches) == 1, 'rank selects multiple/no advertisements')
        require(matches[0]['attributes']['communities']['standard'] == [f'65010:{rank}'], 'rank maps to wrong community')
    checks = data[rendered[2]]
    preflight_service = next(x for x in checks if x['kind'] == 'Service')
    require(preflight_service['spec']['type'] == 'NodePort' and preflight_service['spec']['ipFamilyPolicy'] == 'RequireDualStack', 'preflight must not allocate an LB VIP')
    require(not any(selected(a['selector'], preflight_service) for a in [*ads, *rank_ads]), 'preflight service matches BGP advertisement')
    for path in rendered[3:6]:
        cm = next(x for x in data[path] if x.get('kind') == 'ConfigMap' and x['metadata']['name'] == 'cilium-config')['data']
        require(cm.get('enable-egress-gateway', 'false') == 'false' and cm['enable-bpf-masquerade'] == 'false', 'render enabled Egress')
    print(f'PASS: {len(tn)} topology definitions / {len(tl)} links; existing topology preserved')
    print('PASS: Node addresses, non-overlapping CIDRs, three-cluster Mesh, ASN/peer mapping')
    print('PASS: initial Mesh-only exact advertisement; NodePort-only preflight; handover off/ranks')
    print('PASS: Helm-rendered Egress settings disabled; no cluster or runtime access performed')


if __name__ == '__main__':
    main()
