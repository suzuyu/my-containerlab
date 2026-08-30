#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  configure-coredns-upstream.sh --context KUBE_CONTEXT \
    [--upstream DNS_IPV4] [--record OUTPUT_ENV] [--test-name DNS_NAME] [--apply]

Parameter precedence:
  1. --upstream DNS_IPV4
  2. COREDNS_UPSTREAM_DNS environment variable
  3. First non-loopback nameserver in the host /etc/resolv.conf

Without --apply, print the current and proposed CoreDNS forward target without
changing the cluster. With --apply, verify the selected upstream from a Pod,
patch the CoreDNS ConfigMap, restart CoreDNS, and verify Cluster DNS. A failed
post-change check restores the original Corefile.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

context=""
upstream_arg=""
record_file=""
test_name="www.example.com"
apply=false

while (($# > 0)); do
  case "$1" in
    --context)
      (($# >= 2)) || die "--context requires a value"
      context="$2"
      shift 2
      ;;
    --upstream)
      (($# >= 2)) || die "--upstream requires a value"
      upstream_arg="$2"
      shift 2
      ;;
    --record)
      (($# >= 2)) || die "--record requires a value"
      record_file="$2"
      shift 2
      ;;
    --test-name)
      (($# >= 2)) || die "--test-name requires a value"
      test_name="$2"
      shift 2
      ;;
    --apply)
      apply=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$context" ]] || die "--context is required"
[[ "$test_name" =~ ^[A-Za-z0-9.-]+$ && "$test_name" == *.* ]] || \
  die "--test-name must be a DNS name"

for command_name in kubectl awk sed grep cmp python3 mktemp install; do
  command -v "$command_name" >/dev/null 2>&1 || die "$command_name is required"
done

valid_upstream() {
  python3 - "$1" <<'PY'
import ipaddress
import sys

try:
    address = ipaddress.ip_address(sys.argv[1])
except ValueError:
    raise SystemExit(1)

raise SystemExit(
    0 if address.version == 4 and not (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
    ) else 1
)
PY
}

upstream=""
upstream_source=""
if [[ -n "$upstream_arg" ]]; then
  upstream="$upstream_arg"
  upstream_source="--upstream"
elif [[ -n "${COREDNS_UPSTREAM_DNS:-}" ]]; then
  upstream="${COREDNS_UPSTREAM_DNS}"
  upstream_source="COREDNS_UPSTREAM_DNS"
else
  while read -r candidate; do
    if valid_upstream "$candidate"; then
      upstream="$candidate"
      upstream_source="host /etc/resolv.conf"
      break
    fi
  done < <(awk '$1 == "nameserver" {print $2}' /etc/resolv.conf)
fi

[[ -n "$upstream" ]] || \
  die "no Pod-reachable resolver was detected; specify --upstream or COREDNS_UPSTREAM_DNS"
valid_upstream "$upstream" || die "upstream must be a non-loopback unicast IPv4 address: $upstream"

kubectl config get-contexts -o name | grep -Fxq "$context" || \
  die "Kubernetes context not found: $context"
kubectl --context "$context" get --raw=/livez >/dev/null || \
  die "Kubernetes API is not live: $context"
kubectl --context "$context" -n kube-system get configmap coredns >/dev/null || \
  die "kube-system/coredns ConfigMap was not found"

tmp_dir="$(mktemp -d /tmp/coredns-upstream.XXXXXX)"
created_pods=()
cleanup() {
  local pod_name
  for pod_name in "${created_pods[@]}"; do
    kubectl --context "$context" -n kube-system delete pod "$pod_name" \
      --ignore-not-found --wait=false >/dev/null 2>&1 || true
  done
  rm -r -- "$tmp_dir"
}
trap cleanup EXIT

original_corefile="${tmp_dir}/Corefile.original"
proposed_corefile="${tmp_dir}/Corefile.proposed"
patch_file="${tmp_dir}/coredns-patch.yaml"

kubectl --context "$context" -n kube-system get configmap coredns \
  -o jsonpath='{.data.Corefile}' > "$original_corefile"
[[ -s "$original_corefile" ]] || die "CoreDNS Corefile is empty"

if ! awk -v upstream="$upstream" '
  BEGIN { replacements = 0 }
  $1 == "forward" && $2 == "." {
    indent = $0
    sub(/[^[:space:]].*$/, "", indent)
    suffix = index($0, "{") ? " {" : ""
    print indent "forward . " upstream suffix
    replacements++
    next
  }
  { print }
  END { if (replacements != 1) exit 42 }
' "$original_corefile" > "$proposed_corefile"; then
  die "expected exactly one 'forward .' directive in the CoreDNS Corefile"
fi

current_forward="$(awk '$1 == "forward" && $2 == "." {print; exit}' "$original_corefile")"
proposed_forward="$(awk '$1 == "forward" && $2 == "." {print; exit}' "$proposed_corefile")"

printf 'Kubernetes context: %s\n' "$context"
printf 'Resolver source: %s\n' "$upstream_source"
printf 'Selected upstream: %s\n' "$upstream"
printf 'Current CoreDNS: %s\n' "$current_forward"
printf 'Proposed CoreDNS: %s\n' "$proposed_forward"
if [[ -n "$record_file" ]]; then
  printf 'Runtime record: %s\n' "$record_file"
fi

if [[ "$apply" != true ]]; then
  printf 'Check-only completed. Re-run with --apply to change CoreDNS.\n'
  exit 0
fi

readonly check_image='docker.io/curlimages/curl:8.17.0@sha256:43ebaa53d3806db6b1ce4353b6b26ae638ec1c167ee351524b05690f988bb20d'

run_dns_check() {
  local mode="$1"
  local pod_name="coredns-upstream-${mode}-${BASHPID}"
  local result=0
  local overrides=""

  created_pods+=("$pod_name")
  if [[ "$mode" == direct ]]; then
    overrides="{\"spec\":{\"dnsPolicy\":\"None\",\"dnsConfig\":{\"nameservers\":[\"${upstream}\"],\"options\":[{\"name\":\"ndots\",\"value\":\"0\"}]}}}"
    kubectl --context "$context" -n kube-system run "$pod_name" \
      --image="$check_image" --restart=Never --overrides="$overrides" \
      --command -- sleep 300 >/dev/null
  else
    kubectl --context "$context" -n kube-system run "$pod_name" \
      --image="$check_image" --restart=Never \
      --command -- sleep 300 >/dev/null
  fi

  kubectl --context "$context" -n kube-system wait pod/"$pod_name" \
    --for=condition=Ready --timeout=120s >/dev/null || result=$?
  if (( result == 0 )); then
    kubectl --context "$context" -n kube-system exec pod/"$pod_name" -- \
      getent hosts "$test_name" || result=$?
  fi
  kubectl --context "$context" -n kube-system delete pod "$pod_name" \
    --ignore-not-found --wait=true >/dev/null || true
  return "$result"
}

write_patch() {
  local corefile="$1"
  {
    printf '%s\n' 'data:' '  Corefile: |'
    sed 's/^/    /' "$corefile"
  } > "$patch_file"
}

apply_corefile() {
  local corefile="$1"
  write_patch "$corefile"
  kubectl --context "$context" -n kube-system patch configmap coredns \
    --type=merge --patch-file "$patch_file" >/dev/null
}

rollback_corefile() {
  printf 'Restoring the original CoreDNS Corefile.\n' >&2
  apply_corefile "$original_corefile" || true
  kubectl --context "$context" -n kube-system rollout restart deployment/coredns >/dev/null || true
  kubectl --context "$context" -n kube-system rollout status deployment/coredns \
    --timeout=180s >/dev/null || true
}

printf 'Checking direct DNS reachability to %s from a Pod.\n' "$upstream"
run_dns_check direct || die "direct DNS check failed for upstream $upstream"

changed=false
if ! cmp -s "$original_corefile" "$proposed_corefile"; then
  apply_corefile "$proposed_corefile"
  changed=true
fi

if ! kubectl --context "$context" -n kube-system rollout restart deployment/coredns >/dev/null || \
   ! kubectl --context "$context" -n kube-system rollout status deployment/coredns \
      --timeout=180s >/dev/null; then
  [[ "$changed" == true ]] && rollback_corefile
  die "CoreDNS rollout failed"
fi

printf 'Checking %s through Cluster DNS.\n' "$test_name"
if ! run_dns_check cluster; then
  [[ "$changed" == true ]] && rollback_corefile
  die "Cluster DNS check failed after configuring upstream $upstream"
fi

if [[ -n "$record_file" ]]; then
  record_dir="$(dirname "$record_file")"
  mkdir -p "$record_dir"
  record_tmp="$(mktemp "${record_dir}/.coredns-upstream.XXXXXX")"
  printf '%s\n' \
    '# Generated by configure-coredns-upstream.sh. Do not commit this file.' \
    "COREDNS_UPSTREAM_DNS=${upstream}" \
    "COREDNS_TEST_NAME=${test_name}" > "$record_tmp"
  install -m 0644 "$record_tmp" "$record_file"
  rm -f -- "$record_tmp"
fi

kubectl --context "$context" -n kube-system get configmap coredns \
  -o jsonpath='{.data.Corefile}' | \
  awk '$1 == "forward" && $2 == "." {print "Active CoreDNS: " $0}'
printf 'CoreDNS upstream configuration completed successfully.\n'
