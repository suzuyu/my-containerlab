#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  converge-cilium-lab.sh --profile singlesite-final|multisite-final \
    [--context-k02 kind-adc-k02] [--context-k03 kind-bdc-k03] \
    [--coredns-upstream DNS_IPV4] \
    [--output-dir DIR] [--apply]

Without --apply, perform only offline Helm/Kustomize rendering. With --apply,
converge Node labels/routes, Cilium, platform CRs, and Tetragon in dependency
order, then run readiness checks. The script never creates, recreates, or
destroys Containerlab or Kind resources, and it never applies validation apps.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

profile=""
context_k02="kind-adc-k02"
context_k03="kind-bdc-k03"
output_dir=""
coredns_upstream=""
apply=false

while (($# > 0)); do
  case "$1" in
    --profile)
      (($# >= 2)) || die "--profile requires a value"
      profile="$2"
      shift 2
      ;;
    --context-k02)
      (($# >= 2)) || die "--context-k02 requires a value"
      context_k02="$2"
      shift 2
      ;;
    --context-k03)
      (($# >= 2)) || die "--context-k03 requires a value"
      context_k03="$2"
      shift 2
      ;;
    --output-dir)
      (($# >= 2)) || die "--output-dir requires a value"
      output_dir="$2"
      shift 2
      ;;
    --coredns-upstream)
      (($# >= 2)) || die "--coredns-upstream requires a value"
      coredns_upstream="$2"
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

case "$profile" in
  singlesite-final|multisite-final) ;;
  *) die "--profile must be singlesite-final or multisite-final" ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/../../.." && pwd -P)"
if [[ "$profile" == singlesite-final ]]; then
  fabric_root="${repo_root}/nxos_fabric/nxos_singlesite"
else
  fabric_root="${repo_root}/nxos_fabric/nxos_multisite"
fi
client_root="${fabric_root}/k8s_kind/client"
runtime_bin="${client_root}/runtime/bin"
export PATH="${runtime_bin}:${PATH}"

for command_name in helm kubectl cilium docker awk grep; do
  command -v "$command_name" >/dev/null 2>&1 || die "$command_name is missing below ${runtime_bin} or PATH"
done

if [[ -z "$output_dir" ]]; then
  output_dir="$(mktemp -d "/tmp/cilium-lab-${profile}.XXXXXX")"
fi
"${script_dir}/render-cilium-lab.sh" --profile "$profile" --output-dir "$output_dir"

if [[ "$apply" != true ]]; then
  printf 'Check-only completed. No cluster or Node state was changed.\n'
  printf 'Review the rendered files in: %s\n' "$output_dir"
  exit 0
fi

printf 'Applying profile %s. Containerlab and Kind lifecycle remain out of scope.\n' "$profile"

cilium_version="$(awk -F= '$1 == "CILIUM_CHART_VERSION" {print $2}' "${client_root}/chart-versions.env")"
tetragon_version="$(awk -F= '$1 == "TETRAGON_CHART_VERSION" {print $2}' "${client_root}/chart-versions.env")"
cilium_chart="${client_root}/runtime/charts/cilium-${cilium_version}.tgz"
tetragon_chart="${client_root}/runtime/charts/tetragon-${tetragon_version}.tgz"
[[ -f "$cilium_chart" ]] || die "Cilium chart is missing: ${cilium_chart}"
[[ -f "$tetragon_chart" ]] || die "Tetragon chart is missing: ${tetragon_chart}"

require_context() {
  local context="$1"
  kubectl config get-contexts -o name | grep -Fxq "$context" || die "kube context not found: ${context}"
  kubectl --context "$context" get --raw=/livez >/dev/null || die "Kubernetes API is not live: ${context}"
}

prepare_site() {
  local site="$1"
  local cluster="$2"
  local context="$3"
  local site_root="${fabric_root}/k8s_kind/${site}"

  require_context "$context"
  "${script_dir}/configure-cilium-node-labels.sh" --context "$context" --apply
  "${script_dir}/preflight-host-and-kind.sh" --cluster "$cluster" --kube-context "$context"
  "${script_dir}/render-k8s-api-values.sh" \
    --cluster "$cluster" \
    --output "${site_root}/cilium/runtime/10-k8s-api.yaml"
}

install_cilium() {
  local site="$1"
  local context="$2"
  local overlay="$3"
  local site_root="${fabric_root}/k8s_kind/${site}"

  helm upgrade --install cilium "$cilium_chart" \
    --namespace kube-system \
    --kube-context "$context" \
    --values "${site_root}/cilium/values/00-base.yaml" \
    --values "${site_root}/cilium/values/10-observability.yaml" \
    --values "${site_root}/cilium/values/${overlay}" \
    --values "${site_root}/cilium/runtime/10-k8s-api.yaml" \
    --wait --timeout 10m
  cilium status --context "$context" --wait
}

configure_coredns() {
  local site="$1"
  local context="$2"
  local site_root="${fabric_root}/k8s_kind/${site}"
  local args=(
    --context "$context"
    --record "${site_root}/cilium/runtime/20-coredns-upstream.env"
    --apply
  )

  if [[ -n "$coredns_upstream" ]]; then
    args+=(--upstream "$coredns_upstream")
  fi
  "${script_dir}/configure-coredns-upstream.sh" "${args[@]}"
}

apply_platform_resources() {
  local site="$1"
  local cluster="$2"
  local context="$3"
  local include_clustermesh="$4"
  local site_root="${fabric_root}/k8s_kind/${site}"

  "${script_dir}/configure-bgp-aggregate-blackhole.sh" --cluster "$cluster" --action apply
  kubectl --context "$context" apply \
    -f "${site_root}/cilium/resources/10-lb-ipam.yaml" \
    -f "${site_root}/cilium/resources/20-bgp.yaml" \
    -f "${site_root}/cilium/resources/21-bgp-planned-shut.yaml"
  if [[ "$include_clustermesh" == true ]]; then
    kubectl --context "$context" apply \
      -f "${site_root}/cilium/resources/30-clustermesh-apiserver-service.yaml"
  fi
}

install_tetragon() {
  local site="$1"
  local context="$2"
  local site_root="${fabric_root}/k8s_kind/${site}"

  helm upgrade --install tetragon "$tetragon_chart" \
    --namespace kube-system \
    --kube-context "$context" \
    --values "${site_root}/tetragon/values/00-observe-only.yaml" \
    --wait --timeout 10m
  kubectl --context "$context" -n kube-system rollout status daemonset/tetragon --timeout=5m
  kubectl --context "$context" -n kube-system rollout status deployment/tetragon-operator --timeout=5m
}

accept_site() {
  local context="$1"
  cilium status --context "$context" --wait
  cilium bgp peers --context "$context"
  kubectl --context "$context" get ciliumbgpclusterconfigs,ciliumbgppeerconfigs,ciliumbgpadvertisements
  kubectl --context "$context" -n kube-system get pods -o wide
}

if [[ "$profile" == singlesite-final ]]; then
  prepare_site k02 adc-k02 "$context_k02"
  install_cilium k02 "$context_k02" 20-singlesite-egress.yaml
  configure_coredns k02 "$context_k02"
  apply_platform_resources k02 adc-k02 "$context_k02" false
  install_tetragon k02 "$context_k02"
  accept_site "$context_k02"
else
  prepare_site k02 adc-k02 "$context_k02"
  install_cilium k02 "$context_k02" 20-multisite-clustermesh.yaml
  configure_coredns k02 "$context_k02"
  apply_platform_resources k02 adc-k02 "$context_k02" true

  prepare_site k03 bdc-k03 "$context_k03"
  "${script_dir}/prepare-clustermesh-shared-ca.sh" \
    --source-context "$context_k02" \
    --target-context "$context_k03" \
    --apply
  install_cilium k03 "$context_k03" 20-multisite-clustermesh.yaml
  configure_coredns k03 "$context_k03"
  apply_platform_resources k03 bdc-k03 "$context_k03" true

  install_tetragon k02 "$context_k02"
  install_tetragon k03 "$context_k03"
  accept_site "$context_k02"
  accept_site "$context_k03"
  cilium clustermesh status --context "$context_k02" --wait
  cilium clustermesh status --context "$context_k03" --wait
fi

printf 'Profile %s converged. Validation workloads were not applied.\n' "$profile"
printf 'Offline render evidence: %s\n' "$output_dir"
