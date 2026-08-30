#!/usr/bin/env bash

set -euo pipefail

readonly KUBELET_FLAGS_FILE="${KUBELET_FLAGS_FILE:-/var/lib/kubelet/kubeadm-flags.env}"

if [[ -z "${KUBELET_NODE_IP:-}" ]]; then
  echo "KUBELET_NODE_IP is required" >&2
  exit 1
fi

if [[ ! -f "${KUBELET_FLAGS_FILE}" ]]; then
  echo "kubelet flags file not found: ${KUBELET_FLAGS_FILE}" >&2
  exit 1
fi

IFS=',' read -r -a node_addresses <<< "${KUBELET_NODE_IP}"
for address in "${node_addresses[@]}"; do
  if [[ "${address}" == *:* ]]; then
    address_output="$(ip -6 -o address show to "${address}" 2>/dev/null || true)"
  else
    address_output="$(ip -4 -o address show to "${address}" 2>/dev/null || true)"
  fi

  if [[ -z "${address_output}" ]]; then
    echo "node address is not configured locally: ${address}" >&2
    exit 1
  fi
done

if grep -Fq -- "--node-ip=${KUBELET_NODE_IP}" "${KUBELET_FLAGS_FILE}"; then
  echo "kubelet node IP is already configured: ${KUBELET_NODE_IP}"
  exit 0
fi

tmp_file="$(mktemp "${KUBELET_FLAGS_FILE}.XXXXXX")"
trap 'rm -f "${tmp_file}"' EXIT

if grep -q -- '--node-ip=' "${KUBELET_FLAGS_FILE}"; then
  sed -E "s#--node-ip=[^\"[:space:]]+#--node-ip=${KUBELET_NODE_IP}#" \
    "${KUBELET_FLAGS_FILE}" > "${tmp_file}"
else
  sed -E "s#\"$# --node-ip=${KUBELET_NODE_IP}\"#" \
    "${KUBELET_FLAGS_FILE}" > "${tmp_file}"
fi

if ! grep -Fq -- "--node-ip=${KUBELET_NODE_IP}" "${tmp_file}"; then
  echo "failed to update kubelet node IP" >&2
  exit 1
fi

install -m 0644 "${tmp_file}" "${KUBELET_FLAGS_FILE}"
systemctl restart kubelet
systemctl is-active --quiet kubelet

echo "configured kubelet node IP: ${KUBELET_NODE_IP}"
