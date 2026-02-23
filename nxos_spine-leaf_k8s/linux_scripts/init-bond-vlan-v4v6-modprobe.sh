#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# init-bond-singlevlan.sh
# - Create LACP bond0 (802.3ad) on eth1+eth2
# - Create a single VLAN sub-interface bond0.<VLAN_ID>
# - Assign IPv4/IPv6 address and default routes
#
# Required env:
#   VLAN_ID   : e.g. 101
#   IP_CIDR   : e.g. 192.168.101.11/24
#   DEF_GW    : e.g. 192.168.101.1
#
# Optional env:
#   IPV6_CIDR : e.g. 2001:db8:101::11/64
#   DEF_GW6   : e.g. 2001:db8:101::1
# ============================================================

# ---- required vars ----
: "${VLAN_ID:?VLAN_ID is required (e.g. 101)}"
: "${IP_CIDR:?IP_CIDR is required (e.g. 192.168.101.11/24)}"
: "${DEF_GW:?DEF_GW is required (e.g. 192.168.101.1)}"

# ---- optional vars ----
IPV6_CIDR="${IPV6_CIDR:-}"
DEF_GW6="${DEF_GW6:-}"

VIF="bond0.${VLAN_ID}"

log() { echo "[$(date +'%F %T')] $*"; }

# ------------------------------------------------------------
# Best-effort: try to load required kernel modules
# NOTE:
#  - bonding/8021q are HOST kernel features.
#  - In typical containerlab linux nodes, modprobe often fails
#    (not privileged / no /lib/modules mount). We try anyway.
# ------------------------------------------------------------
try_modprobe() {
  local m="$1"
  if lsmod | awk '{print $1}' | grep -qx "$m"; then
    log "[OK] module already loaded: $m"
    return 0
  fi

  if command -v modprobe >/dev/null 2>&1; then
    if modprobe "$m" >/dev/null 2>&1; then
      log "[INFO] loaded module: $m"
      return 0
    else
      log "[WARN] modprobe $m failed (likely not privileged / no /lib/modules mount)."
      return 1
    fi
  else
    log "[WARN] modprobe not found in container."
    return 1
  fi
}

try_modprobe bonding || true
try_modprobe 8021q   || true

# ------------------------------------------------------------
# Sanity checks
# ------------------------------------------------------------
if ! ip link show eth1 >/dev/null 2>&1 || ! ip link show eth2 >/dev/null 2>&1; then
  log "[ERROR] eth1/eth2 not found. Check containerlab links."
  ip link show || true
  exit 1
fi

# Check if bonding is actually available by attempting to create a test bond.
if ! ip link add __bond_test type bond >/dev/null 2>&1; then
  log "[ERROR] Cannot create bonding interface. Host kernel module 'bonding' is not available/loaded."
  log "[ERROR] Fix on host: sudo modprobe bonding && sudo modprobe 8021q"
  exit 1
else
  ip link del __bond_test >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------
# Create bond0 (LACP)
# ------------------------------------------------------------
if ip link show bond0 >/dev/null 2>&1; then
  log "[INFO] bond0 already exists; reconfiguring slaves/state."
else
  log "[INFO] creating bond0 (802.3ad LACP)"
  ip link add bond0 type bond mode 802.3ad miimon 100 lacp_rate fast
fi

# (Re)attach slaves safely
ip link set eth1 down || true
ip link set eth2 down || true
ip link set eth1 master bond0 || true
ip link set eth2 master bond0 || true

ip link set bond0 up
ip link set eth1 up
ip link set eth2 up

# ------------------------------------------------------------
# Create single VLAN sub-interface on bond0
# ------------------------------------------------------------
if ip link show "${VIF}" >/dev/null 2>&1; then
  log "[INFO] ${VIF} already exists"
else
  log "[INFO] creating VLAN sub-interface ${VIF} (id ${VLAN_ID})"
  ip link add link bond0 name "${VIF}" type vlan id "${VLAN_ID}"
fi
ip link set "${VIF}" up

# ------------------------------------------------------------
# IPv4 address + default route
# ------------------------------------------------------------
log "[INFO] configuring IPv4 on ${VIF}: ${IP_CIDR}"
ip addr replace "${IP_CIDR}" dev "${VIF}"

log "[INFO] configuring IPv4 default route via ${DEF_GW}"
ip route replace default via "${DEF_GW}" dev "${VIF}"

# ------------------------------------------------------------
# IPv6 address + default route (optional)
# ------------------------------------------------------------
if [[ -n "${IPV6_CIDR}" ]]; then
  log "[INFO] enabling IPv6 sysctls (best-effort)"
  sysctl -w net.ipv6.conf.all.disable_ipv6=0 >/dev/null 2>&1 || true
  sysctl -w net.ipv6.conf.default.disable_ipv6=0 >/dev/null 2>&1 || true
  sysctl -w "net.ipv6.conf.${VIF}.disable_ipv6=0" >/dev/null 2>&1 || true

  log "[INFO] configuring IPv6 on ${VIF}: ${IPV6_CIDR}"
  ip -6 addr replace "${IPV6_CIDR}" dev "${VIF}"

  if [[ -n "${DEF_GW6}" ]]; then
    log "[INFO] configuring IPv6 default route via ${DEF_GW6}"
    ip -6 route replace default via "${DEF_GW6}" dev "${VIF}"
  else
    log "[INFO] DEF_GW6 not set; skipping IPv6 default route (RA may still work if present)."
  fi
fi

# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------
log "[INFO] done. Current link/address/route summary:"
ip -d link show bond0 || true
ip -d link show "${VIF}" || true
ip addr show dev "${VIF}" || true
ip route || true
ip -6 route || true
