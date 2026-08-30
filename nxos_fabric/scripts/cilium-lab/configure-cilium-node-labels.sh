#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 --context CONTEXT [--apply]

Without --apply, verify that exactly two worker Nodes have bgp-speaker=true
and the single control-plane Node does not. With --apply, converge those labels
and then perform the same verification.
EOF
}

KUBE_CONTEXT=""
APPLY=false
while (($# > 0)); do
  case "$1" in
    --context)
      (($# >= 2)) || { usage >&2; exit 2; }
      KUBE_CONTEXT="$2"
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$KUBE_CONTEXT" ]] || { usage >&2; exit 2; }

mapfile -t CONTROL_PLANE_NODES < <(
  kubectl --context "$KUBE_CONTEXT" get nodes \
    -l node-role.kubernetes.io/control-plane \
    -o name
)
mapfile -t WORKER_NODES < <(
  kubectl --context "$KUBE_CONTEXT" get nodes \
    -l '!node-role.kubernetes.io/control-plane' \
    -o name
)

if [ "${#CONTROL_PLANE_NODES[@]}" -ne 1 ]; then
  printf 'Expected 1 control-plane node, found %d.\n' "${#CONTROL_PLANE_NODES[@]}" >&2
  exit 1
fi

if [ "${#WORKER_NODES[@]}" -ne 2 ]; then
  printf 'Expected 2 worker nodes, found %d.\n' "${#WORKER_NODES[@]}" >&2
  exit 1
fi

if [[ "$APPLY" == true ]]; then
  for node in "${CONTROL_PLANE_NODES[@]}"; do
    label_value="$(kubectl --context "$KUBE_CONTEXT" get "$node" -o jsonpath='{.metadata.labels.bgp-speaker}')"
    if [[ -n "$label_value" ]]; then
      kubectl --context "$KUBE_CONTEXT" label "$node" bgp-speaker-
    fi
  done
  kubectl --context "$KUBE_CONTEXT" label "${WORKER_NODES[@]}" \
    bgp-speaker=true \
    --overwrite
fi

kubectl --context "$KUBE_CONTEXT" get nodes \
  -L node-role.kubernetes.io/control-plane,bgp-speaker

for node in "${CONTROL_PLANE_NODES[@]}"; do
  label_value="$(kubectl --context "$KUBE_CONTEXT" get "$node" -o jsonpath='{.metadata.labels.bgp-speaker}')"
  [[ -z "$label_value" ]] || {
    printf 'Control-plane Node must not have bgp-speaker: %s=%s\n' "$node" "$label_value" >&2
    exit 1
  }
done

for node in "${WORKER_NODES[@]}"; do
  label_value="$(kubectl --context "$KUBE_CONTEXT" get "$node" -o jsonpath='{.metadata.labels.bgp-speaker}')"
  [[ "$label_value" == true ]] || {
    printf 'Worker Node must have bgp-speaker=true: %s=%s\n' "$node" "${label_value:-<unset>}" >&2
    exit 1
  }
done

printf 'BGP speaker labels are converged for context %s.\n' "$KUBE_CONTEXT"
