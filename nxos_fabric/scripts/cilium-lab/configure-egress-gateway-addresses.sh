#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  configure-egress-gateway-addresses.sh --cluster adc-k02 \
    --action check|apply|remove

The script manages the dedicated Egress Gateway secondary addresses on the
two k02 worker Kind node containers. Cilium does not allocate these addresses.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cluster=""
action=""

while (($# > 0)); do
  case "$1" in
    --cluster)
      (($# >= 2)) || die "--cluster requires a value"
      cluster="$2"
      shift 2
      ;;
    --action)
      (($# >= 2)) || die "--action requires a value"
      action="$2"
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

[[ "$cluster" == adc-k02 ]] || die "only adc-k02 is defined for the initial Egress Gateway test"
case "$action" in
  check|apply|remove) ;;
  *) die "--action must be check, apply, or remove" ;;
esac

command -v docker >/dev/null 2>&1 || die "docker is required"

nodes=(adc-k02-worker adc-k02-worker2)
interfaces=(bond0.14 bond0.104)
primary_v4=(172.16.4.21/24 172.16.4.22/24)
egress_v4=(172.16.4.31/24 172.16.4.32/24)
egress_v6=(fd21:0:0:4::3:1/64 fd21:0:0:4::3:2/64)

address_present() {
  local node="$1"
  local family="$2"
  local interface="$3"
  local address="$4"
  if [[ "$family" == v4 ]]; then
    docker exec "$node" ip -o -4 addr show dev "$interface" | awk '{print $4}' | grep -Fxq "$address"
  else
    docker exec "$node" ip -o -6 addr show dev "$interface" | awk '{print $4}' | grep -Fxq "$address"
  fi
}

failed=false
for index in "${!nodes[@]}"; do
  node="${nodes[$index]}"
  interface="${interfaces[$index]}"
  address_v4="${egress_v4[$index]}"
  address_v6="${egress_v6[$index]}"

  docker inspect "$node" >/dev/null 2>&1 || die "container not found: $node"
  docker exec "$node" ip link show dev "$interface" >/dev/null 2>&1 || die "$node is missing $interface"
  address_present "$node" v4 "$interface" "${primary_v4[$index]}" || \
    die "$node $interface is missing expected primary address ${primary_v4[$index]}"

  case "$action" in
    apply)
      address_present "$node" v4 "$interface" "$address_v4" || \
        docker exec "$node" ip addr add "$address_v4" dev "$interface"
      address_present "$node" v6 "$interface" "$address_v6" || \
        docker exec "$node" ip -6 addr add "$address_v6" dev "$interface" nodad
      ;;
    remove)
      if address_present "$node" v4 "$interface" "$address_v4"; then
        docker exec "$node" ip addr del "$address_v4" dev "$interface"
      fi
      if address_present "$node" v6 "$interface" "$address_v6"; then
        docker exec "$node" ip -6 addr del "$address_v6" dev "$interface"
      fi
      ;;
  esac

  has_v4=false
  has_v6=false
  address_present "$node" v4 "$interface" "$address_v4" && has_v4=true
  address_present "$node" v6 "$interface" "$address_v6" && has_v6=true
  printf '%s %s IPv4=%s IPv6=%s\n' "$node" "$interface" "$has_v4" "$has_v6"

  if [[ "$action" == check || "$action" == apply ]]; then
    [[ "$has_v4" == true && "$has_v6" == true ]] || failed=true
  else
    [[ "$has_v4" == false && "$has_v6" == false ]] || failed=true
  fi
done

[[ "$failed" == false ]] || die "Egress Gateway address validation failed"
