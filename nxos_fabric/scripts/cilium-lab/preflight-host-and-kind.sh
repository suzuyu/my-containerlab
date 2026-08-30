#!/usr/bin/env bash
set -uo pipefail

MIN_AVAILABLE_MIB=8192
MIN_KERNEL=5.10.0
EXPECTED_NODE_IMAGE="kindest/node:v1.35.5@sha256:ce977ae6d65918d0b58a5f8b5e940429c2ce42fa3a5619ec2bbc60b949c0ac95"
CLUSTER=""
KUBE_CONTEXT=""
HOST_ONLY=false

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

usage() {
  cat <<'EOF'
Usage:
  preflight-host-and-kind.sh [options]

Options:
  --cluster adc-k02|bdc-k03   Check the expected Kind nodes and Fabric links.
  --kube-context CONTEXT      Also verify the worker-only BGP speaker labels.
  --host-only                 Check only the host requirements.
  --min-available-mib MIB     Required host MemAvailable value. Default: 8192.
  --expected-node-image IMG   Expected Kind node image including its digest.
  -h, --help                  Show this help.
EOF
}

pass() {
  printf 'PASS: %s\n' "$*"
  PASS_COUNT=$((PASS_COUNT + 1))
}

warn() {
  printf 'WARN: %s\n' "$*"
  WARN_COUNT=$((WARN_COUNT + 1))
}

fail() {
  printf 'FAIL: %s\n' "$*"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

version_ge() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n 1)" = "$2" ]
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --cluster)
      CLUSTER="${2:-}"
      shift 2
      ;;
    --kube-context)
      KUBE_CONTEXT="${2:-}"
      shift 2
      ;;
    --host-only)
      HOST_ONLY=true
      shift
      ;;
    --min-available-mib)
      MIN_AVAILABLE_MIB="${2:-}"
      shift 2
      ;;
    --expected-node-image)
      EXPECTED_NODE_IMAGE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$MIN_AVAILABLE_MIB" =~ ^[0-9]+$ ]]; then
  printf '%s\n' '--min-available-mib must be an integer.' >&2
  exit 2
fi

if [ "$HOST_ONLY" = false ] && [ -z "$CLUSTER" ]; then
  printf '%s\n' '--cluster is required unless --host-only is specified.' >&2
  exit 2
fi

if [ -n "$CLUSTER" ] && [ "$CLUSTER" != "adc-k02" ] && [ "$CLUSTER" != "bdc-k03" ]; then
  printf '%s\n' '--cluster must be adc-k02 or bdc-k03.' >&2
  exit 2
fi

if [ -n "$KUBE_CONTEXT" ]; then
  if ! command -v kubectl >/dev/null 2>&1; then
    printf 'kubectl is required when --kube-context is specified.\n' >&2
    exit 2
  fi
  if ! kubectl config get-contexts "$KUBE_CONTEXT" -o name 2>/dev/null |
    grep -Fxq "$KUBE_CONTEXT"; then
    printf 'Kubernetes context is unavailable: %s\n' "$KUBE_CONTEXT" >&2
    printf 'Set KUBECONFIG to the Containerlab-generated kubeconfig before retrying.\n' >&2
    exit 2
  fi
  if ! kubectl --context "$KUBE_CONTEXT" get nodes --request-timeout=10s >/dev/null; then
    printf 'Kubernetes API is unreachable through context: %s\n' "$KUBE_CONTEXT" >&2
    exit 2
  fi
fi

printf '%s\n' '## Host preflight'

for command_name in awk sort stat uname; do
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "command is available: ${command_name}"
  else
    fail "required command is missing: ${command_name}"
  fi
done

HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
  x86_64|aarch64)
    pass "supported host architecture: ${HOST_ARCH}"
    ;;
  *)
    fail "unsupported host architecture: ${HOST_ARCH}"
    ;;
esac

HOST_KERNEL="$(uname -r | sed 's/-.*//')"
if version_ge "$HOST_KERNEL" "$MIN_KERNEL"; then
  pass "kernel ${HOST_KERNEL} is at least ${MIN_KERNEL}"
else
  fail "kernel ${HOST_KERNEL} is older than ${MIN_KERNEL}"
fi

if [ "$(stat -fc %T /sys/fs/cgroup 2>/dev/null || true)" = "cgroup2fs" ]; then
  pass 'cgroup v2 is mounted at /sys/fs/cgroup'
else
  fail 'cgroup v2 is not mounted at /sys/fs/cgroup'
fi

if [ -r /sys/kernel/btf/vmlinux ]; then
  pass 'kernel BTF is available at /sys/kernel/btf/vmlinux'
else
  fail 'kernel BTF is unavailable at /sys/kernel/btf/vmlinux'
fi

MEM_AVAILABLE_MIB="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)"
if [ "$MEM_AVAILABLE_MIB" -ge "$MIN_AVAILABLE_MIB" ]; then
  pass "MemAvailable ${MEM_AVAILABLE_MIB} MiB is at least ${MIN_AVAILABLE_MIB} MiB"
else
  fail "MemAvailable ${MEM_AVAILABLE_MIB} MiB is below ${MIN_AVAILABLE_MIB} MiB"
fi

SWAP_TOTAL_KIB="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
SWAP_FREE_KIB="$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)"
if [ "$SWAP_TOTAL_KIB" -eq "$SWAP_FREE_KIB" ]; then
  pass 'swap is not in use'
else
  warn "swap is in use: $(((SWAP_TOTAL_KIB - SWAP_FREE_KIB) / 1024)) MiB"
fi

for rp_filter_path in /proc/sys/net/ipv4/conf/all/rp_filter /proc/sys/net/ipv4/conf/default/rp_filter; do
  if [ -r "$rp_filter_path" ]; then
    RP_FILTER_VALUE="$(<"$rp_filter_path")"
    if [ "$RP_FILTER_VALUE" -eq 0 ]; then
      pass "${rp_filter_path} is 0"
    elif [ "$RP_FILTER_VALUE" -eq 1 ]; then
      fail "${rp_filter_path} is strict mode 1"
    else
      warn "${rp_filter_path} is loose mode ${RP_FILTER_VALUE}; asymmetric paths must be tested"
    fi
  else
    warn "cannot read ${rp_filter_path}"
  fi
done

KERNEL_CONFIG=""
if [ -r "/boot/config-$(uname -r)" ]; then
  KERNEL_CONFIG="/boot/config-$(uname -r)"
elif [ -r /proc/config.gz ] && command -v zgrep >/dev/null 2>&1; then
  KERNEL_CONFIG=/proc/config.gz
fi

REQUIRED_KERNEL_CONFIGS=(
  CONFIG_BPF
  CONFIG_BPF_EVENTS
  CONFIG_BPF_SYSCALL
  CONFIG_BPF_JIT
  CONFIG_DEBUG_INFO_BTF
  CONFIG_CRYPTO_SHA1
  CONFIG_CRYPTO_USER_API_HASH
  CONFIG_CGROUPS
  CONFIG_CGROUP_BPF
  CONFIG_NET_CLS_BPF
  CONFIG_NET_CLS_ACT
  CONFIG_NET_SCH_INGRESS
  CONFIG_PERF_EVENTS
  CONFIG_SCHEDSTATS
  CONFIG_VXLAN
  CONFIG_GENEVE
  CONFIG_FIB_RULES
  CONFIG_NETFILTER_XT_SET
  CONFIG_IP_SET
  CONFIG_IP_SET_HASH_IP
  CONFIG_NETFILTER_XT_MATCH_COMMENT
  CONFIG_NETFILTER_XT_TARGET_TPROXY
  CONFIG_NETFILTER_XT_TARGET_MARK
  CONFIG_NETFILTER_XT_TARGET_CT
  CONFIG_NETFILTER_XT_MATCH_MARK
  CONFIG_NETFILTER_XT_MATCH_SOCKET
)

if [ -n "$KERNEL_CONFIG" ]; then
  for kernel_option in "${REQUIRED_KERNEL_CONFIGS[@]}"; do
    if [ "$KERNEL_CONFIG" = /proc/config.gz ]; then
      KERNEL_OPTION_VALUE="$(zgrep -E "^${kernel_option}=(y|m)$" "$KERNEL_CONFIG" 2>/dev/null || true)"
    else
      KERNEL_OPTION_VALUE="$(grep -E "^${kernel_option}=(y|m)$" "$KERNEL_CONFIG" 2>/dev/null || true)"
    fi
    if [ -n "$KERNEL_OPTION_VALUE" ]; then
      pass "$KERNEL_OPTION_VALUE"
    else
      fail "${kernel_option} is not y or m in ${KERNEL_CONFIG}"
    fi
  done
else
  warn 'kernel config is not readable; required CONFIG_BPF/CGROUP/VXLAN options were not verified'
fi

if [ "$HOST_ONLY" = true ]; then
  printf '\nSUMMARY: PASS=%d WARN=%d FAIL=%d\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
  [ "$FAIL_COUNT" -eq 0 ]
  exit $?
fi

printf '\n%s\n' "## Kind node preflight: ${CLUSTER}"

if ! command -v docker >/dev/null 2>&1; then
  fail 'docker is required for Kind node checks'
  printf '\nSUMMARY: PASS=%d WARN=%d FAIL=%d\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
  exit 1
fi

case "$CLUSTER" in
  adc-k02)
    NODE_SPECS=(
      'adc-k02-control-plane|bond0.14|172.16.4.11|fd21::4:0:0:1:1|false'
      'adc-k02-worker|bond0.14|172.16.4.21|fd21::4:0:0:2:1|true'
      'adc-k02-worker2|bond0.104|172.16.4.22|fd21::4:0:0:2:2|true'
    )
    ROUTE4='172.16.0.0/16 via 172.16.4.1'
    ROUTE6='fd21::/48 via fd21:0:0:4::1'
    ;;
  bdc-k03)
    NODE_SPECS=(
      'bdc-k03-control-plane|bond0.105|172.16.5.11|fd21::5:0:0:1:1|false'
      'bdc-k03-worker|bond0.105|172.16.5.21|fd21::5:0:0:2:1|true'
      'bdc-k03-worker2|bond0.105|172.16.5.22|fd21::5:0:0:2:2|true'
    )
    ROUTE4='172.16.0.0/16 via 172.16.5.1'
    ROUTE6='fd21::/48 via fd21:0:0:5::1'
    ;;
esac

HOST_CGROUP_NS="$(readlink /proc/self/ns/cgroup 2>/dev/null || true)"
NODE_CGROUP_NAMESPACES=()

for node_spec in "${NODE_SPECS[@]}"; do
  IFS='|' read -r node_name fabric_interface ipv4_address ipv6_address bgp_speaker <<<"$node_spec"

  if ! docker inspect "$node_name" >/dev/null 2>&1; then
    fail "Kind node container does not exist: ${node_name}"
    continue
  fi

  NODE_RUNNING="$(docker inspect --format '{{.State.Running}}' "$node_name" 2>/dev/null || true)"
  if [ "$NODE_RUNNING" = true ]; then
    pass "Kind node is running: ${node_name}"
  else
    fail "Kind node is not running: ${node_name}"
    continue
  fi

  NODE_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$node_name" 2>/dev/null || true)"
  if [ "$NODE_IMAGE" = "$EXPECTED_NODE_IMAGE" ]; then
    pass "${node_name} image matches ${EXPECTED_NODE_IMAGE}"
  else
    fail "${node_name} image is ${NODE_IMAGE}; expected ${EXPECTED_NODE_IMAGE}"
  fi

  NODE_CGROUP_TYPE="$(docker exec "$node_name" stat -fc %T /sys/fs/cgroup 2>/dev/null || true)"
  if [ "$NODE_CGROUP_TYPE" = cgroup2fs ]; then
    pass "${node_name} uses cgroup v2"
  else
    fail "${node_name} does not use cgroup v2"
  fi

  NODE_CGROUP_NS="$(docker exec "$node_name" readlink /proc/self/ns/cgroup 2>/dev/null || true)"
  NODE_CGROUP_NAMESPACES+=("$NODE_CGROUP_NS")
  if [ -n "$NODE_CGROUP_NS" ] && [ "$NODE_CGROUP_NS" != "$HOST_CGROUP_NS" ]; then
    pass "${node_name} has a cgroup namespace separate from the host"
  else
    fail "${node_name} does not have a separate cgroup namespace"
  fi

  if docker exec "$node_name" test -r /sys/kernel/btf/vmlinux; then
    pass "${node_name} can read kernel BTF"
  else
    fail "${node_name} cannot read kernel BTF"
  fi

  NODE_BPF_FSTYPE="$(docker exec "$node_name" stat -fc %T /sys/fs/bpf 2>/dev/null || true)"
  if [ "$NODE_BPF_FSTYPE" = bpf_fs ]; then
    pass "${node_name} has bpffs mounted"
  else
    warn "${node_name} has no bpffs mount yet; bpf.autoMount.enabled must mount it during Cilium install"
  fi

  if docker exec "$node_name" ip link show "$fabric_interface" >/dev/null 2>&1; then
    pass "${node_name} has ${fabric_interface}"
  else
    fail "${node_name} is missing ${fabric_interface}"
    continue
  fi

  NODE_MTU="$(docker exec "$node_name" cat "/sys/class/net/${fabric_interface}/mtu" 2>/dev/null || true)"
  if [ "$NODE_MTU" = 9100 ]; then
    pass "${node_name} ${fabric_interface} MTU is 9100"
  else
    fail "${node_name} ${fabric_interface} MTU is ${NODE_MTU}; expected 9100"
  fi

  NODE_ADDR_OUTPUT="$(docker exec "$node_name" ip -brief address show "$fabric_interface" 2>/dev/null || true)"
  if [[ "$NODE_ADDR_OUTPUT" == *"${ipv4_address}/24"* ]]; then
    pass "${node_name} has ${ipv4_address}/24 on ${fabric_interface}"
  else
    fail "${node_name} is missing ${ipv4_address}/24 on ${fabric_interface}"
  fi
  if [[ "$NODE_ADDR_OUTPUT" == *"${ipv6_address}/64"* ]]; then
    pass "${node_name} has ${ipv6_address}/64 on ${fabric_interface}"
  else
    fail "${node_name} is missing ${ipv6_address}/64 on ${fabric_interface}"
  fi

  if docker exec "$node_name" ip route show | grep -Fq "${ROUTE4} dev ${fabric_interface}"; then
    pass "${node_name} has the expected IPv4 Fabric aggregate route"
  else
    fail "${node_name} is missing IPv4 route: ${ROUTE4} dev ${fabric_interface}"
  fi
  if docker exec "$node_name" ip -6 route show | grep -Fq "${ROUTE6} dev ${fabric_interface}"; then
    pass "${node_name} has the expected IPv6 Fabric aggregate route"
  else
    fail "${node_name} is missing IPv6 route: ${ROUTE6} dev ${fabric_interface}"
  fi

  if [ -z "$KUBE_CONTEXT" ]; then
    warn "BGP speaker label was not checked for ${node_name}; pass --kube-context to verify it"
  else
    if ! NODE_BGP_LABEL="$(kubectl --context "$KUBE_CONTEXT" get node "$node_name" \
      -o jsonpath='{.metadata.labels.bgp-speaker}')"; then
      fail "unable to read BGP speaker label for ${node_name}"
      continue
    fi
    if [ "$bgp_speaker" = true ] && [ "$NODE_BGP_LABEL" = true ]; then
      pass "${node_name} is selected as a BGP speaker"
    elif [ "$bgp_speaker" = false ] && [ -z "$NODE_BGP_LABEL" ]; then
      pass "${node_name} is excluded from BGP speaker selection"
    elif [ "$bgp_speaker" = true ]; then
      fail "${node_name} must have bgp-speaker=true"
    else
      fail "${node_name} control-plane must not have bgp-speaker"
    fi
  fi
done

UNIQUE_CGROUP_NS_COUNT="$(printf '%s\n' "${NODE_CGROUP_NAMESPACES[@]}" | sed '/^$/d' | sort -u | wc -l)"
if [ "$UNIQUE_CGROUP_NS_COUNT" -eq "${#NODE_SPECS[@]}" ]; then
  pass 'all Kind nodes have distinct cgroup namespaces'
else
  fail "only ${UNIQUE_CGROUP_NS_COUNT} distinct Kind cgroup namespaces were found"
fi

printf '\nSUMMARY: PASS=%d WARN=%d FAIL=%d\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
[ "$FAIL_COUNT" -eq 0 ]
