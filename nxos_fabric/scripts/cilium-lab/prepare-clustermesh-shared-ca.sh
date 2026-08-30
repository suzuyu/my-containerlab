#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  prepare-clustermesh-shared-ca.sh \
    --source-context kind-adc-k02 \
    --target-context kind-bdc-k03 \
    [--apply | --replace-existing]

Without --apply, the script only checks whether source and target cilium-ca
Secrets exist and whether their CA certificates match. With --apply, it copies
the source cilium-ca into an absent target Secret and verifies the certificate
fingerprint. An existing different CA is never changed by --apply; use
--replace-existing only during an explicitly reviewed maintenance operation.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

source_context=""
target_context=""
apply=false
replace_existing=false

while (($# > 0)); do
  case "$1" in
    --source-context)
      (($# >= 2)) || die "--source-context requires a value"
      source_context="$2"
      shift 2
      ;;
    --target-context)
      (($# >= 2)) || die "--target-context requires a value"
      target_context="$2"
      shift 2
      ;;
    --apply)
      apply=true
      shift
      ;;
    --replace-existing)
      apply=true
      replace_existing=true
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

[[ -n "$source_context" ]] || die "--source-context is required"
[[ -n "$target_context" ]] || die "--target-context is required"

for command_name in kubectl openssl base64 mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || die "$command_name is required"
done

source_crt_b64="$(kubectl --context "$source_context" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}')"
[[ -n "$source_crt_b64" ]] || die "source cilium-ca does not contain ca.crt"
source_fp="$(printf '%s' "$source_crt_b64" | base64 -d | openssl x509 -noout -fingerprint -sha256)"

target_exists=false
if kubectl --context "$target_context" -n kube-system get secret cilium-ca >/dev/null 2>&1; then
  target_exists=true
  target_crt_b64="$(kubectl --context "$target_context" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}')"
  target_fp="$(printf '%s' "$target_crt_b64" | base64 -d | openssl x509 -noout -fingerprint -sha256)"
  printf 'source: %s\ntarget: %s\n' "$source_fp" "$target_fp"
  if [[ "$source_fp" == "$target_fp" ]]; then
    printf 'Cluster Mesh CA fingerprints match.\n'
    exit 0
  fi
fi

[[ "$apply" == true ]] || die "target CA is absent or different; rerun with --apply after reviewing the contexts"
if [[ "$target_exists" == true && "$replace_existing" != true ]]; then
  die "target CA is different; --apply will not replace it. Use --replace-existing only in a reviewed maintenance operation"
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
source_key_b64="$(kubectl --context "$source_context" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.key}')"
[[ -n "$source_key_b64" ]] || die "source cilium-ca does not contain ca.key"
printf '%s' "$source_crt_b64" | base64 -d > "${tmp_dir}/ca.crt"
printf '%s' "$source_key_b64" | base64 -d > "${tmp_dir}/ca.key"
chmod 0600 "${tmp_dir}/ca.crt" "${tmp_dir}/ca.key"

if [[ "$target_exists" == true ]]; then
  patch_file="${tmp_dir}/cilium-ca-patch.json"
  printf '{"data":{"ca.crt":"%s","ca.key":"%s"}}\n' \
    "$source_crt_b64" "$source_key_b64" > "$patch_file"
  chmod 0600 "$patch_file"
  kubectl --context "$target_context" -n kube-system patch secret cilium-ca \
    --type=merge --patch-file "$patch_file"
else
  kubectl --context "$target_context" -n kube-system create secret generic cilium-ca \
    --from-file=ca.crt="${tmp_dir}/ca.crt" \
    --from-file=ca.key="${tmp_dir}/ca.key"
fi

target_crt_b64="$(kubectl --context "$target_context" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}')"
target_fp="$(printf '%s' "$target_crt_b64" | base64 -d | openssl x509 -noout -fingerprint -sha256)"
printf 'source: %s\ntarget: %s\n' "$source_fp" "$target_fp"
[[ "$source_fp" == "$target_fp" ]] || die "copied Cluster Mesh CA fingerprint does not match"
