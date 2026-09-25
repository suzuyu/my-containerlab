# Source from bash. Runtime files and credentials stay outside Git.
UREH_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$(cd -- "$UREH_DIR/../../../.." && pwd)"
export LAB_ROOT="$REPO_ROOT/nxos_fabric/nxos_multisite"
export PATH="$LAB_ROOT/k8s_kind/client/runtime/bin:$PATH"
export KUBECONFIG="$LAB_ROOT/clab-nxos-fabric-multisite/adc-k02/k8s_kind/k02/kubeconfig-k02:$LAB_ROOT/clab-nxos-fabric-multisite/bdc-k03/k8s_kind/k03/kubeconfig-k03:$LAB_ROOT/k8s_kind/k04/kubeconfig-k04"
export UREH_DIR
