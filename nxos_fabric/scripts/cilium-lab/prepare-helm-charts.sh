#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  prepare-helm-charts.sh --profile <k8s_kind/client> [--check] [--force]

Charts are downloaded from the official Cilium chart sources into the profile's
Git-ignored runtime/charts directory. The Helm binary must already be prepared
by scripts/k8s-client/prepare-tools.sh.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

profile_dir=""
check_only=false
force=false

while (($# > 0)); do
  case "$1" in
    --profile)
      (($# >= 2)) || die "--profile requires a directory"
      profile_dir="$2"
      shift 2
      ;;
    --check)
      check_only=true
      shift
      ;;
    --force)
      force=true
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

[[ -n "$profile_dir" ]] || die "--profile is required"
profile_dir="$(cd "$profile_dir" && pwd -P)"
versions_file="${profile_dir}/chart-versions.env"
helm_bin="${profile_dir}/runtime/bin/helm"
chart_dir="${profile_dir}/runtime/charts"

[[ -f "$versions_file" ]] || die "missing chart version file: $versions_file"
[[ -x "$helm_bin" ]] || die "missing Helm binary: run prepare-tools.sh first"

CILIUM_CHART_VERSION=""
TETRAGON_CHART_VERSION=""
while IFS='=' read -r key value; do
  [[ -n "$key" ]] || continue
  case "$key" in
    CILIUM_CHART_VERSION) CILIUM_CHART_VERSION="$value" ;;
    TETRAGON_CHART_VERSION) TETRAGON_CHART_VERSION="$value" ;;
    *) die "unsupported key in $versions_file: $key" ;;
  esac
done < "$versions_file"

for value_name in CILIUM_CHART_VERSION TETRAGON_CHART_VERSION; do
  value="${!value_name}"
  [[ "$value" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$ ]] || \
    die "$value_name must be an explicit version, got: ${value:-<empty>}"
done

mkdir -p "$chart_dir"
cilium_chart="${chart_dir}/cilium-${CILIUM_CHART_VERSION}.tgz"
tetragon_chart="${chart_dir}/tetragon-${TETRAGON_CHART_VERSION}.tgz"

chart_matches() {
  local path="$1"
  local expected_name="$2"
  local expected_version="$3"
  [[ -f "$path" ]] || return 1
  "$helm_bin" show chart "$path" | \
    awk -F': ' -v name="$expected_name" -v version="$expected_version" '
      $1 == "name" && $2 == name {name_ok=1}
      $1 == "version" && $2 == version {version_ok=1}
      END {exit !(name_ok && version_ok)}
    '
}

if [[ "$check_only" == true ]]; then
  chart_matches "$cilium_chart" cilium "$CILIUM_CHART_VERSION" || die "Cilium chart cache is missing or invalid"
  chart_matches "$tetragon_chart" tetragon "$TETRAGON_CHART_VERSION" || die "Tetragon chart cache is missing or invalid"
  printf 'Chart cache is ready: %s\n' "$chart_dir"
  exit 0
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

if [[ "$force" == true ]] || ! chart_matches "$cilium_chart" cilium "$CILIUM_CHART_VERSION"; then
  "$helm_bin" pull oci://quay.io/cilium/charts/cilium \
    --version "$CILIUM_CHART_VERSION" \
    --destination "$tmp_dir"
  install -m 0644 "${tmp_dir}/cilium-${CILIUM_CHART_VERSION}.tgz" "$cilium_chart"
fi

if [[ "$force" == true ]] || ! chart_matches "$tetragon_chart" tetragon "$TETRAGON_CHART_VERSION"; then
  "$helm_bin" pull tetragon \
    --repo https://helm.cilium.io \
    --version "$TETRAGON_CHART_VERSION" \
    --destination "$tmp_dir"
  install -m 0644 "${tmp_dir}/tetragon-${TETRAGON_CHART_VERSION}.tgz" "$tetragon_chart"
fi

chart_matches "$cilium_chart" cilium "$CILIUM_CHART_VERSION" || die "downloaded Cilium chart validation failed"
chart_matches "$tetragon_chart" tetragon "$TETRAGON_CHART_VERSION" || die "downloaded Tetragon chart validation failed"
printf 'Chart cache is ready: %s\n' "$chart_dir"
