#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# init-bond-singlevlan.sh (containerlab/kind friendly)
# - Create LACP bond0 (802.3ad) on eth1+eth2
# - Create a single VLAN sub-interface bond0.<VLAN_ID>
# - Assign IPv4/IPv6 address
# - (Optional) Set default routes (disabled by default to avoid breaking kind/k8s)
# - (Optional) Add static routes for node routing (NEW)
# - Set MTU on bond/VLAN/slaves (default 9000)
#
# Required env:
#   VLAN_ID   : e.g. 101
#   IP_CIDR   : e.g. 192.168.101.11/24
#
# Optional env:
#   DEF_GW    : e.g. 192.168.101.1        (only used if SET_DEFAULT_ROUTE=true)
#   IPV6_CIDR : e.g. 2001:db8:101::11/64
#   DEF_GW6   : e.g. 2001:db8:101::1      (only used if SET_DEFAULT_ROUTE=true)
#   MTU       : e.g. 9000 (default 9000)
#   SET_DEFAULT_ROUTE : "true"|"false" (default false)
#
#   (NEW) ROUTES4 : newline-separated static routes to add (IPv4)
#     Examples:
#       ROUTES4=$'10.10.0.0/16 via 192.168.101.1\n172.16.0.0/12 dev bond0.101'
#       ROUTES4=$'10.10.0.0/16 via 192.168.101.1 metric 50'
#
#   (NEW) ROUTES6 : newline-separated static routes to add (IPv6)
#     Examples:
#       ROUTES6=$'2001:db8:200::/64 via 2001:db8:101::1\n2001:db8:300::/64 dev bond0.101'
#
#   BOND_MODE : e.g. 802.3ad (default 802.3ad)
#   MIIMON    : e.g. 100 (default 100)
#   LACP_RATE : e.g. fast|slow (default fast)
#   XMIT_HASH_POLICY : e.g. layer3+4 (default layer3+4)
# ============================================================

# ---- required vars ----
: "${VLAN_ID:?VLAN_ID is required (e.g. 101)}"
: "${IP_CIDR:?IP_CIDR is required (e.g. 192.168.101.11/24)}"

# ---- optional vars ----
DEF_GW="${DEF_GW:-}"
IPV6_CIDR="${IPV6_CIDR:-}"
DEF_GW6="${DEF_GW6:-}"

MTU="${MTU:-9000}"
SET_DEFAULT_ROUTE="${SET_DEFAULT_ROUTE:-false}"

# NEW: static routes
ROUTES4="${ROUTES4:-}"
ROUTES6="${ROUTES6:-}"

BOND_MODE="${BOND_MODE:-802.3ad}"
MIIMON="${MIIMON:-100}"
LACP_RATE="${LACP_RATE:-fast}"
XMIT_HASH_POLICY="${XMIT_HASH_POLICY:-layer3+4}"

VIF="bond0.${VLAN_ID}"

log() { echo "[$(date +'%F %T')] $*"; }

# ------------------------------------------------------------
# Best-effort: try to load required kernel modules
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
# Helpers: add routes (NEW)
# ------------------------------------------------------------
add_routes_v4() {
  local routes="$1"
  [[ -z "$routes" ]] && return 0

  log "[INFO] adding IPv4 static routes (ROUTES4)"
  # Each non-empty, non-comment line is appended to: ip route replace <line>
  while IFS= read -r line; do
    # trim leading/trailing spaces (bash-safe)
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    log "  [ROUTE4] ip route replace $line"
    ip route replace $line
  done <<< "$routes"
}

add_routes_v6() {
  local routes="$1"
  [[ -z "$routes" ]] && return 0

  log "[INFO] adding IPv6 static routes (ROUTES6)"
  while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    log "  [ROUTE6] ip -6 route replace $line"
    ip -6 route replace $line
  done <<< "$routes"
}

# ------------------------------------------------------------
# Sanity checks
# ------------------------------------------------------------
if ! ip link show eth1 >/dev/null 2>&1 || ! ip link show eth2 >/dev/null 2>&1; then
  log "[ERROR] eth1/eth2 not found. Check containerlab links."
  ip link show || true
  exit 1
fi

# Check if bonding is available by attempting to create a test bond.
if ! ip link add __bond_test type bond >/dev/null 2>&1; then
  log "[ERROR] Cannot create bonding interface. Host kernel module 'bonding' is not available/loaded."
  log "[ERROR] Fix on host: sudo modprobe bonding && sudo modprobe 8021q"
  exit 1
else
  ip link del __bond_test >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------
# Create bond0 (LACP or chosen mode)
# ------------------------------------------------------------
if ip link show bond0 >/dev/null 2>&1; then
  log "[INFO] bond0 already exists; reconfiguring slaves/state."
else
  log "[INFO] creating bond0 (mode=${BOND_MODE})"
  if [[ "${BOND_MODE}" == "802.3ad" ]]; then
    ip link add bond0 type bond \
      mode 802.3ad \
      miimon "${MIIMON}" \
      lacp_rate "${LACP_RATE}" \
      xmit_hash_policy "${XMIT_HASH_POLICY}"
  else
    ip link add bond0 type bond mode "${BOND_MODE}" miimon "${MIIMON}"
  fi
fi

# Attach slaves safely
ip link set eth1 down || true
ip link set eth2 down || true
ip link set eth1 master bond0 || true
ip link set eth2 master bond0 || true

# MTU: set on slaves and bond
log "[INFO] setting MTU=${MTU} on eth1/eth2/bond0"
ip link set eth1 mtu "${MTU}" || true
ip link set eth2 mtu "${MTU}" || true
ip link set bond0 mtu "${MTU}" || true

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

log "[INFO] setting MTU=${MTU} on ${VIF}"
ip link set "${VIF}" mtu "${MTU}" || true
ip link set "${VIF}" up

# ------------------------------------------------------------
# IPv4 address + (optional) default route
# ------------------------------------------------------------
log "[INFO] configuring IPv4 on ${VIF}: ${IP_CIDR}"
ip addr replace "${IP_CIDR}" dev "${VIF}"

if [[ "${SET_DEFAULT_ROUTE}" == "true" ]]; then
  if [[ -z "${DEF_GW}" ]]; then
    log "[ERROR] SET_DEFAULT_ROUTE=true but DEF_GW is not set."
    exit 1
  fi
  log "[WARN] replacing IPv4 default route via ${DEF_GW} on ${VIF}"
  ip route replace default via "${DEF_GW}" dev "${VIF}"
else
  log "[INFO] SET_DEFAULT_ROUTE=false; keeping existing IPv4 default route (likely via eth0)."
fi

# NEW: IPv4 static routes
add_routes_v4 "${ROUTES4}"

# ------------------------------------------------------------
# IPv6 address + (optional) default route
# ------------------------------------------------------------
if [[ -n "${IPV6_CIDR}" ]]; then
  log "[INFO] enabling IPv6 sysctls (best-effort)"
  sysctl -w net.ipv6.conf.all.disable_ipv6=0 >/dev/null 2>&1 || true
  sysctl -w net.ipv6.conf.default.disable_ipv6=0 >/dev/null 2>&1 || true
  sysctl -w "net.ipv6.conf.${VIF}.disable_ipv6=0" >/dev/null 2>&1 || true

  log "[INFO] configuring IPv6 on ${VIF}: ${IPV6_CIDR}"
  ip -6 addr replace "${IPV6_CIDR}" dev "${VIF}"

  if [[ "${SET_DEFAULT_ROUTE}" == "true" ]]; then
    if [[ -z "${DEF_GW6}" ]]; then
      log "[ERROR] SET_DEFAULT_ROUTE=true but DEF_GW6 is not set (for IPv6 default route)."
      exit 1
    fi
    log "[WARN] replacing IPv6 default route via ${DEF_GW6} on ${VIF}"
    ip -6 route replace default via "${DEF_GW6}" dev "${VIF}"
  else
    log "[INFO] SET_DEFAULT_ROUTE=false; keeping existing IPv6 default route."
  fi

  # NEW: IPv6 static routes
  add_routes_v6 "${ROUTES6}"
else
  # IPv6_CIDR無しでも ROUTES6 だけ入れたいケースはあり得るので許可（best-effort）
  if [[ -n "${ROUTES6}" ]]; then
    log "[WARN] ROUTES6 is set but IPV6_CIDR is empty; adding IPv6 routes anyway (best-effort)."
    add_routes_v6 "${ROUTES6}"
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