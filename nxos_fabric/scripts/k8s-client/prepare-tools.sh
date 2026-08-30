#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  prepare-tools.sh --profile <k8s_kind/client> [--check] [--force]

Options:
  --profile DIR  Directory containing tool-versions.env.
  --check        Verify the local runtime cache without downloading.
  --force        Download and replace all tools even when versions match.
  -h, --help     Show this help.

The script writes binaries and local checksums below:
  <profile>/runtime/bin/

The runtime directory is intentionally excluded from Git.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '[k8s-client] %s\n' "$*"
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
[[ -d "$profile_dir" ]] || die "profile directory not found: $profile_dir"

profile_dir="$(cd "$profile_dir" && pwd -P)"
versions_file="${profile_dir}/tool-versions.env"
runtime_dir="${profile_dir}/runtime"
bin_dir="${runtime_dir}/bin"
kubeconfig_dir="${runtime_dir}/kubeconfig"
local_checksums="${bin_dir}/SHA256SUMS.local"

[[ -f "$versions_file" ]] || die "version file not found: $versions_file"

KUBECTL_VERSION=""
CILIUM_CLI_VERSION=""
HUBBLE_CLI_VERSION=""
HELM_VERSION=""

while IFS='=' read -r key value; do
  [[ -n "$key" ]] || continue
  [[ "$key" == \#* ]] && continue
  case "$key" in
    KUBECTL_VERSION) KUBECTL_VERSION="$value" ;;
    CILIUM_CLI_VERSION) CILIUM_CLI_VERSION="$value" ;;
    HUBBLE_CLI_VERSION) HUBBLE_CLI_VERSION="$value" ;;
    HELM_VERSION) HELM_VERSION="$value" ;;
    *) die "unsupported key in $versions_file: $key" ;;
  esac
done < "$versions_file"

for value_name in KUBECTL_VERSION CILIUM_CLI_VERSION HUBBLE_CLI_VERSION HELM_VERSION; do
  value="${!value_name}"
  [[ "$value" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$ ]] || \
    die "$value_name must be an explicit v-prefixed version, got: ${value:-<empty>}"
done

case "$(uname -m)" in
  x86_64) cli_arch="amd64" ;;
  aarch64|arm64) cli_arch="arm64" ;;
  *) die "unsupported architecture: $(uname -m)" ;;
esac

for command_name in curl sha256sum tar mktemp install grep; do
  command -v "$command_name" >/dev/null 2>&1 || die "required command not found: $command_name"
done

mkdir -p "$bin_dir" "$kubeconfig_dir"

tool_reports_version() {
  local tool="$1"
  local expected="$2"
  local path="${bin_dir}/${tool}"
  local output=""

  [[ -x "$path" ]] || return 1
  case "$tool" in
    kubectl) output="$("$path" version --client --output=yaml 2>/dev/null)" || return 1 ;;
    cilium) output="$("$path" version --client 2>/dev/null)" || return 1 ;;
    hubble) output="$("$path" version 2>/dev/null)" || return 1 ;;
    helm) output="$("$path" version --short 2>/dev/null)" || return 1 ;;
    *) return 1 ;;
  esac
  grep -Fq "$expected" <<< "$output"
}

verify_cache() {
  local failed=false

  if [[ ! -f "$local_checksums" ]]; then
    printf 'Missing local checksum manifest: %s\n' "$local_checksums" >&2
    failed=true
  elif ! (cd "$bin_dir" && sha256sum --check --strict "$(basename "$local_checksums")"); then
    failed=true
  fi

  if ! tool_reports_version kubectl "$KUBECTL_VERSION"; then
    printf 'kubectl does not report expected version %s\n' "$KUBECTL_VERSION" >&2
    failed=true
  fi
  if ! tool_reports_version cilium "$CILIUM_CLI_VERSION"; then
    printf 'cilium does not report expected version %s\n' "$CILIUM_CLI_VERSION" >&2
    failed=true
  fi
  if ! tool_reports_version hubble "$HUBBLE_CLI_VERSION"; then
    printf 'hubble does not report expected version %s\n' "$HUBBLE_CLI_VERSION" >&2
    failed=true
  fi
  if ! tool_reports_version helm "$HELM_VERSION"; then
    printf 'helm does not report expected version %s\n' "$HELM_VERSION" >&2
    failed=true
  fi

  [[ "$failed" == false ]]
}

if [[ "$check_only" == true ]]; then
  verify_cache || die "tool cache validation failed; run without --check to prepare it"
  log "tool cache is ready: $bin_dir"
  exit 0
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
stage_dir="${tmp_dir}/stage"
mkdir -p "$stage_dir"

curl_args=(--fail --location --silent --show-error --retry 3 --connect-timeout 15)

download_kubectl() {
  local binary="kubectl"
  local checksum="kubectl.sha256"
  local base_url="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${cli_arch}"

  log "downloading kubectl ${KUBECTL_VERSION} (${cli_arch})"
  curl "${curl_args[@]}" --output "${tmp_dir}/${binary}" "${base_url}/${binary}"
  curl "${curl_args[@]}" --output "${tmp_dir}/${checksum}" "${base_url}/${binary}.sha256"
  printf '%s  %s\n' "$(tr -d '[:space:]' < "${tmp_dir}/${checksum}")" "${tmp_dir}/${binary}" | \
    sha256sum --check --strict -
  install -m 0755 "${tmp_dir}/${binary}" "${stage_dir}/${binary}"
}

download_release_archive() {
  local tool="$1"
  local version="$2"
  local repository="$3"
  local archive="${tool}-linux-${cli_arch}.tar.gz"
  local checksum="${archive}.sha256sum"
  local base_url="https://github.com/${repository}/releases/download/${version}"
  local extract_dir="${tmp_dir}/extract-${tool}"

  log "downloading ${tool} ${version} (${cli_arch})"
  curl "${curl_args[@]}" --output "${tmp_dir}/${archive}" "${base_url}/${archive}"
  curl "${curl_args[@]}" --output "${tmp_dir}/${checksum}" "${base_url}/${checksum}"
  (cd "$tmp_dir" && sha256sum --check --strict "$checksum")

  mkdir -p "$extract_dir"
  tar -xzf "${tmp_dir}/${archive}" -C "$extract_dir"
  [[ -f "${extract_dir}/${tool}" ]] || die "$archive did not contain expected binary: $tool"
  install -m 0755 "${extract_dir}/${tool}" "${stage_dir}/${tool}"
}

download_helm() {
  local archive="helm-${HELM_VERSION}-linux-${cli_arch}.tar.gz"
  local checksum="${archive}.sha256sum"
  local base_url="https://get.helm.sh"
  local extract_dir="${tmp_dir}/extract-helm"

  log "downloading helm ${HELM_VERSION} (${cli_arch})"
  curl "${curl_args[@]}" --output "${tmp_dir}/${archive}" "${base_url}/${archive}"
  curl "${curl_args[@]}" --output "${tmp_dir}/${checksum}" "${base_url}/${checksum}"
  (cd "$tmp_dir" && sha256sum --check --strict "$checksum")

  mkdir -p "$extract_dir"
  tar -xzf "${tmp_dir}/${archive}" -C "$extract_dir"
  [[ -f "${extract_dir}/linux-${cli_arch}/helm" ]] || \
    die "$archive did not contain expected binary: linux-${cli_arch}/helm"
  install -m 0755 "${extract_dir}/linux-${cli_arch}/helm" "${stage_dir}/helm"
}

need_kubectl=true
need_cilium=true
need_hubble=true
need_helm=true

if [[ "$force" == false ]] && tool_reports_version kubectl "$KUBECTL_VERSION"; then
  need_kubectl=false
  log "using cached kubectl ${KUBECTL_VERSION}"
fi
if [[ "$force" == false ]] && tool_reports_version cilium "$CILIUM_CLI_VERSION"; then
  need_cilium=false
  log "using cached cilium ${CILIUM_CLI_VERSION}"
fi
if [[ "$force" == false ]] && tool_reports_version hubble "$HUBBLE_CLI_VERSION"; then
  need_hubble=false
  log "using cached hubble ${HUBBLE_CLI_VERSION}"
fi
if [[ "$force" == false ]] && tool_reports_version helm "$HELM_VERSION"; then
  need_helm=false
  log "using cached helm ${HELM_VERSION}"
fi

[[ "$need_kubectl" == false ]] || download_kubectl
[[ "$need_cilium" == false ]] || \
  download_release_archive cilium "$CILIUM_CLI_VERSION" cilium/cilium-cli
[[ "$need_hubble" == false ]] || \
  download_release_archive hubble "$HUBBLE_CLI_VERSION" cilium/hubble
[[ "$need_helm" == false ]] || download_helm

[[ "$need_kubectl" == false ]] || install -m 0755 "${stage_dir}/kubectl" "${bin_dir}/kubectl"
[[ "$need_cilium" == false ]] || install -m 0755 "${stage_dir}/cilium" "${bin_dir}/cilium"
[[ "$need_hubble" == false ]] || install -m 0755 "${stage_dir}/hubble" "${bin_dir}/hubble"
[[ "$need_helm" == false ]] || install -m 0755 "${stage_dir}/helm" "${bin_dir}/helm"

(
  cd "$bin_dir"
  sha256sum kubectl cilium hubble helm > "$(basename "$local_checksums")"
)

verify_cache || die "download completed but validation failed"
log "tool cache is ready: $bin_dir"
log "kubeconfig directory is ready: $kubeconfig_dir"
