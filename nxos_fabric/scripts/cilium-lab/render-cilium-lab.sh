#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  render-cilium-lab.sh --profile singlesite-final|multisite-final \
    --output-dir DIR

This command performs offline Helm and Kustomize rendering only. It does not
connect to a cluster and does not apply resources.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

profile=""
output_dir=""
while (($# > 0)); do
  case "$1" in
    --profile)
      (($# >= 2)) || die "--profile requires a value"
      profile="$2"
      shift 2
      ;;
    --output-dir)
      (($# >= 2)) || die "--output-dir requires a value"
      output_dir="$2"
      shift 2
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
  *) die "unsupported profile: ${profile:-<empty>}" ;;
esac
[[ -n "$output_dir" ]] || die "--output-dir is required"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/../../.." && pwd -P)"

if [[ "$profile" == singlesite-final ]]; then
  fabric_root="${repo_root}/nxos_fabric/nxos_singlesite"
else
  fabric_root="${repo_root}/nxos_fabric/nxos_multisite"
fi

client_root="${fabric_root}/k8s_kind/client"
helm_bin="${client_root}/runtime/bin/helm"
kubectl_bin="${client_root}/runtime/bin/kubectl"
[[ -x "$helm_bin" ]] || die "Helm runtime is missing below $client_root"
[[ -x "$kubectl_bin" ]] || die "kubectl runtime is missing below $client_root"

# Resolve chart versions from the profile lock without evaluating shell code.
cilium_version="$(awk -F= '$1 == "CILIUM_CHART_VERSION" {print $2}' "${client_root}/chart-versions.env")"
tetragon_version="$(awk -F= '$1 == "TETRAGON_CHART_VERSION" {print $2}' "${client_root}/chart-versions.env")"
cilium_chart="${client_root}/runtime/charts/cilium-${cilium_version}.tgz"
tetragon_chart="${client_root}/runtime/charts/tetragon-${tetragon_version}.tgz"
[[ -f "$cilium_chart" ]] || die "Cilium chart cache is missing: run prepare-helm-charts.sh"
[[ -f "$tetragon_chart" ]] || die "Tetragon chart cache is missing: run prepare-helm-charts.sh"

mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd -P)"

render_kustomizations() {
  local root="$1"
  local prefix="$2"
  local kustomization=""
  while IFS= read -r kustomization; do
    relative="${kustomization#${root}/}"
    relative="${relative%/kustomization.yaml}"
    safe_name="${relative//\//-}"
    "$kubectl_bin" kustomize "$(dirname "$kustomization")" > "${output_dir}/${prefix}-${safe_name}.yaml"
  done < <(find "$root" -name kustomization.yaml -type f | sort)
}

render_site() {
  local site="$1"
  local overlay="$2"
  local site_root="${fabric_root}/k8s_kind/${site}"
  "$helm_bin" template cilium "$cilium_chart" \
    --namespace kube-system \
    --values "${site_root}/cilium/values/00-base.yaml" \
    --values "${site_root}/cilium/values/10-observability.yaml" \
    --values "${site_root}/cilium/values/${overlay}" \
    --set k8sServiceHost=192.0.2.10 \
    --set k8sServicePort=6443 \
    > "${output_dir}/${site}-cilium.yaml"

  "$helm_bin" template tetragon "$tetragon_chart" \
    --namespace kube-system \
    --values "${site_root}/tetragon/values/00-observe-only.yaml" \
    > "${output_dir}/${site}-tetragon.yaml"

  if [[ -f "${site_root}/cilium/resources/kustomization.yaml" ]]; then
    "$kubectl_bin" kustomize "${site_root}/cilium/resources" \
      > "${output_dir}/${site}-platform-resources.yaml"
  fi

  if [[ -d "${site_root}/cilium/manifests" ]]; then
    render_kustomizations "${site_root}/cilium/manifests" "$site"
  fi
}

if [[ "$profile" == singlesite-final ]]; then
  render_site k02 20-singlesite-egress.yaml
else
  render_site k02 20-multisite-clustermesh.yaml
  render_site k03 20-multisite-clustermesh.yaml
fi

(
  cd "$output_dir"
  sha256sum ./*.yaml > SHA256SUMS
)
printf 'Offline render completed: %s\n' "$output_dir"
