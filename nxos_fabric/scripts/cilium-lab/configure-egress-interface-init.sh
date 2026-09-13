#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: configure-egress-interface-init.sh --context kind-adc-k02 --action check|apply|restart

Manage the single-site k02 Egress initializer. check is read-only. apply
converges labels and resources, restarting Pods only if nodes.json changed.
restart also reruns initialization when host addresses need repair.
No Cilium Helm, BGP advertisement, Egress Policy, or Node restart is performed.
EOF
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
context=""
action=""
while (($#)); do
  case "$1" in
    --context|--action)
      (($# >= 2)) || die "$1 requires a value"
      case "$1" in --context) context="$2";; --action) action="$2";; esac
      shift 2;;
    -h|--help) usage; exit 0;;
    *) usage >&2; die "unknown argument: $1";;
  esac
done
[[ "$context" == kind-adc-k02 ]] || die "only kind-adc-k02 is supported"
case "$action" in check|apply|restart) ;; *) usage >&2; exit 2;; esac
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/../../.." && pwd -P)"
manifest_root="${repo_root}/nxos_fabric/nxos_singlesite/k8s_kind/k02/cilium/manifests/egress-interface-init"
for cmd in kubectl jq python3 docker cmp; do command -v "$cmd" >/dev/null || die "$cmd is missing"; done
k() { kubectl --context "$context" "$@"; }
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
k create --dry-run=client -f "${manifest_root}/configmap.yaml" -o json > "$work/config.json"
jq -er '.data["nodes.json"]' "$work/config.json" > "$work/nodes.json"
k get nodes -o json > "$work/cluster-nodes.json"
python3 - "$work/nodes.json" "$work/cluster-nodes.json" <<'PY'
import ipaddress, json, sys
desired = json.load(open(sys.argv[1]))
nodes = json.load(open(sys.argv[2]))['items']
expected = {'adc-k02-control-plane', 'adc-k02-worker', 'adc-k02-worker2'}
if {n['metadata']['name'] for n in nodes} != expected:
    sys.exit('unexpected cluster membership; no changes made')
if set(desired) != expected - {'adc-k02-control-plane'}:
    sys.exit('nodes.json must name the two k02 workers')
seen = set()
for name, config in desired.items():
    expected_interface = 'bond0.14' if name == 'adc-k02-worker' else 'bond0.104'
    if config['fabricInterface'] != expected_interface:
        sys.exit(f'{name}: unexpected Fabric interface')
    for family, version, prefix in [('ipv4', 4, 32), ('ipv6', 6, 128)]:
        if not config[family]:
            sys.exit(f'{name}: {family} must not be empty')
        for text in config[family]:
            addr = ipaddress.ip_interface(text)
            if addr.version != version or addr.network.prefixlen != prefix or str(addr) != text:
                sys.exit(f'{name}: use canonical /{prefix} {family} addresses')
            if addr.ip in seen:
                sys.exit(f'duplicate address: {addr.ip}')
            seen.add(addr.ip)
PY
for node in adc-k02-control-plane adc-k02-worker adc-k02-worker2; do
  docker exec "$node" ip -j address show > "$work/${node}-addresses.json"
  docker exec "$node" ip -d -j link show > "$work/${node}-links.json"
done
python3 - "$work" <<'PY'
import ipaddress, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
desired = json.loads((p/'nodes.json').read_text())
owners = {ipaddress.ip_interface(a).ip: n for n, c in desired.items()
          for f in ('ipv4','ipv6') for a in c[f]}
for node in ('adc-k02-control-plane', 'adc-k02-worker', 'adc-k02-worker2'):
    links = json.loads((p/f'{node}-links.json').read_text())
    for link in links:
        if link['ifname'] == 'egress0' and (node not in desired or
                link.get('ifalias') != 'cilium-lab-egress:adc-k02' or
                link.get('linkinfo', {}).get('info_kind') != 'dummy'):
            sys.exit(f'{node}: unexpected egress0 ownership/type; no changes made')
    for dev in json.loads((p/f'{node}-addresses.json').read_text()):
        for rec in dev.get('addr_info', []):
            address = ipaddress.ip_address(rec['local'])
            if address in owners and (node != owners[address] or dev['ifname'] != 'egress0'):
                sys.exit(f'{address} is already on {node}/{dev["ifname"]}; no changes made')
PY
for node in adc-k02-worker adc-k02-worker2; do
  docker exec "$node" bash -ec 'for c in bash ip jq mkdir sleep stat touch; do command -v "$c" >/dev/null; done'
done

if [[ "$action" != check ]]; then
  k apply --dry-run=server -k "$manifest_root"
  k -n kube-system get configmap k02-egress-interface-config --ignore-not-found -o json > "$work/old-config.json"
  changed=false
  if [[ -s "$work/old-config.json" ]]; then
    old="$(jq -r '.data["nodes.json"]' "$work/old-config.json" | jq -Sc .)"
    new="$(jq -Sc . "$work/nodes.json")"
    [[ "$old" == "$new" ]] || changed=true
  fi
  # The complete k02 membership and host preflight above precede all writes.
  if jq -e '.items[] | select(.metadata.name == "adc-k02-control-plane") |
      .metadata.labels | has("lab.cilium.io/egress-gateway")' "$work/cluster-nodes.json" >/dev/null; then
    k label node adc-k02-control-plane lab.cilium.io/egress-gateway-
  fi
  k label node adc-k02-worker adc-k02-worker2 lab.cilium.io/egress-gateway=true --overwrite
  k apply -k "$manifest_root"
  if [[ "$changed" == true || "$action" == restart ]]; then
    k -n kube-system rollout restart daemonset/k02-egress-interface-init
  fi
  k -n kube-system rollout status daemonset/k02-egress-interface-init --timeout=240s
fi
k -n kube-system get configmap k02-egress-interface-config -o json |
  jq -er '.data["nodes.json"]' | jq -Sc . > "$work/live-nodes.json"
jq -Sc . "$work/nodes.json" > "$work/desired-nodes.json"
cmp -s "$work/live-nodes.json" "$work/desired-nodes.json" || die "ConfigMap differs from the local desired state"
k get nodes -o json > "$work/cluster-nodes-after.json"
jq -e '[.items[] | select(.metadata.labels["lab.cilium.io/egress-gateway"] == "true") |
  .metadata.name] | sort == ["adc-k02-worker", "adc-k02-worker2"]' "$work/cluster-nodes-after.json" >/dev/null
k -n kube-system get daemonset k02-egress-interface-init -o json > "$work/daemonset.json"
jq -e '.status.observedGeneration == .metadata.generation and
  .status.desiredNumberScheduled == 2 and .status.numberReady == 2 and
  .status.updatedNumberScheduled == 2 and (.status.numberMisscheduled // 0) == 0' "$work/daemonset.json" >/dev/null
k -n kube-system get pods -l app.kubernetes.io/name=egress-interface-init,app.kubernetes.io/instance=k02 -o json > "$work/pods.json"
python3 - "$work" <<'PY'
import ipaddress, json, pathlib, subprocess, sys
p = pathlib.Path(sys.argv[1])
desired = json.loads((p/'nodes.json').read_text())
pods = json.loads((p/'pods.json').read_text())['items']
if len(pods) != 2 or {pod['spec']['nodeName'] for pod in pods} != set(desired):
    sys.exit('initializer Pods must be on exactly the two target nodes')
for pod in pods:
    node = pod['spec']['nodeName']
    uid = pod['metadata']['uid']
    subprocess.run(['docker','exec',node,'test','-f',f'/run/cilium-egress-interface-init/{uid}'], check=True)
    data = json.loads(subprocess.check_output(['docker','exec',node,'ip','-j','address','show','dev','egress0']))
    have = set()
    for dev in data:
        if 'UP' not in dev['flags']:
            sys.exit(f'{node}: egress0 is down')
        for a in dev.get('addr_info', []):
            if a.get('scope') != 'global':
                continue
            if a.get('tentative') or a.get('dadfailed') or set(a.get('flags',[])) & {'tentative','dadfailed'}:
                sys.exit(f'{node}: address is not ready')
            have.add(ipaddress.ip_interface(f'{a["local"]}/{a["prefixlen"]}'))
    want = {ipaddress.ip_interface(a) for f in ('ipv4','ipv6') for a in desired[node][f]}
    if have != want:
        sys.exit(f'{node}: address drift; use --action restart to reconcile')
    print(f'{node} egress0 addresses=OK checkpoint=OK')
PY
printf 'Egress initializer %s completed for %s.\n' "$action" "$context"
