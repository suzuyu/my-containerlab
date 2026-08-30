#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  configure-bgp-aggregate-blackhole.sh --cluster adc-k02|bdc-k03 \
    --action check|apply|remove

The script configures the site LoadBalancer aggregate as a blackhole route on
the two worker Kind node containers. It never changes the control-plane node.
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

case "$cluster" in
  adc-k02)
    nodes=(adc-k02-worker adc-k02-worker2)
    prefix_v4="172.16.14.0/26"
    prefix_v6="fd21:0:0:14:0:0:1:0/112"
    ;;
  bdc-k03)
    nodes=(bdc-k03-worker bdc-k03-worker2)
    prefix_v4="172.16.15.0/26"
    prefix_v6="fd21:0:0:15:0:0:1:0/112"
    ;;
  *)
    die "--cluster must be adc-k02 or bdc-k03"
    ;;
esac

case "$action" in
  check|apply|remove) ;;
  *) die "--action must be check, apply, or remove" ;;
esac

command -v docker >/dev/null 2>&1 || die "docker is required"

route_line() {
  local node="$1"
  local family="$2"
  local prefix="$3"
  if [[ "$family" == v4 ]]; then
    docker exec "$node" ip route show exact "$prefix"
  else
    docker exec "$node" ip -6 route show exact "$prefix"
  fi
}

apply_route() {
  local node="$1"
  local family="$2"
  local prefix="$3"
  local current=""
  current="$(route_line "$node" "$family" "$prefix")"
  if [[ -n "$current" && "$current" != blackhole\ * ]]; then
    die "$node has a non-blackhole route for $prefix: $current"
  fi
  if [[ "$family" == v4 ]]; then
    docker exec "$node" ip route replace blackhole "$prefix" metric 42760
  else
    docker exec "$node" ip -6 route replace blackhole "$prefix" metric 42760
  fi
}

remove_route() {
  local node="$1"
  local family="$2"
  local prefix="$3"
  local current=""
  current="$(route_line "$node" "$family" "$prefix")"
  [[ -n "$current" ]] || return 0
  [[ "$current" == blackhole\ * ]] || die "refusing to remove non-blackhole route: $current"
  if [[ "$family" == v4 ]]; then
    docker exec "$node" ip route del blackhole "$prefix"
  else
    docker exec "$node" ip -6 route del blackhole "$prefix"
  fi
}

failed=false
for node in "${nodes[@]}"; do
  docker inspect "$node" >/dev/null 2>&1 || die "container not found: $node"
  case "$action" in
    apply)
      apply_route "$node" v4 "$prefix_v4"
      apply_route "$node" v6 "$prefix_v6"
      ;;
    remove)
      remove_route "$node" v4 "$prefix_v4"
      remove_route "$node" v6 "$prefix_v6"
      ;;
  esac

  current_v4="$(route_line "$node" v4 "$prefix_v4")"
  current_v6="$(route_line "$node" v6 "$prefix_v6")"
  printf '%s\n  IPv4: %s\n  IPv6: %s\n' "$node" "${current_v4:-<absent>}" "${current_v6:-<absent>}"

  if [[ "$action" == check || "$action" == apply ]]; then
    [[ "$current_v4" == blackhole\ * ]] || failed=true
    [[ "$current_v6" == blackhole\ * ]] || failed=true
  else
    [[ -z "$current_v4" ]] || failed=true
    [[ -z "$current_v6" ]] || failed=true
  fi
done

[[ "$failed" == false ]] || die "aggregate blackhole route validation failed"
