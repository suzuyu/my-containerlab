# adc-k02 Cilium 構築：段階導入と最終構成の一括導入

この README は multisite の `adc-k02` を段階的に導入して試験する方法と、
個別試験を行わず両クラスタを現在の最終構成で導入する方法をまとめる。
コマンドは Containerlab 実行ホストの `nxos_fabric/nxos_multisite` で実行する。
初回は k02 の Cilium と CA を先に作り、k03 へ CA を共有してから k03 の Cilium を導入する。

2026-09-25 に k04 を含む 3 クラスタの接続先を稼働環境へ追加した。
本書の通常時用 values／`multisite-final` は 2 クラスタの基準を維持する。
**k04 接続中の再適用では、[k04 手順の 3 クラスタ用 overlay](../../k04/cilium/README.md#k04-three-cluster-values)を最後に重ねる。**
従来の一括手順だけでは接続先から k04 が外れる。
[今回の導入・検証記録](../../../../docs/cilium-lab/results/multisite/2026-09-25/k04-clustermesh.md)を併せて参照する。

## 最初に確認：初期導入と最終構成の差分

ここで「初期」は、パターン A の **Cilium の初回 Helm install 直後**を指す。
「最終」は、checksum など必要な初期化と全常設コンポーネントの導入を完了した状態を指す。
**A の基盤構築完了時と B の完了時は同じ設定になる。** 試験の実施を理由に MTU や機能フラグを切り替える構成ではない。
以下は保存済み設定と導入手順の比較であり、稼働環境を今回再確認した結果ではない。


| 対象 | 初期：各クラスタの Cilium 導入直後 | 最終：両クラスタの常設基盤完成時 | 差分・適用タイミング |
|---|---|---|---|
| Leaf／Fabric | L2／Fabric MTU `9216`、LACP 設定済みが前提 | 初期から変更なし | Cilium 導入前に構築・確認。一括 driver では変更しない |
| Cilium | `v1.20.1`、dual-stack、外側 IPv4 VXLAN、kube-proxy replacement。Node Fabric `9150`、Cilium 基準 `9050`、Pod 経路 `9000` | 初期から変更なし | 初回から最終 values を使用 |
| Node IP | Fabric IPv4／IPv6 を InternalIP、Fabric IPv4 を VXLAN 終端に使用。API bootstrap は control-plane の管理 eth0 | 初期から変更なし | 方式は同じ。再構築時は API values を再生成 |
| Hubble | Agent／Relay 有効。UI は k02 のみ | 初期から変更なし | Cilium と同時に導入 |
| Cluster Mesh | API 2 replica・PDB を初回から設定。k03 は共有 CA を準備して導入。外部 API Service／経路の設定は後続 | API は各 2 replica、共通 CA、PDB `minAvailable: 1`、固定 dual-stack VIP、Service `ClientIP` affinity | 後続で固定 VIP Service・LB／BGP を揃える。両クラスタ完成後に Mesh 接続を確認 |
| LB／BGP | BGP feature と worker speaker label は有効。pool／BGP CR／集約 route／外部 Mesh Service は未適用 | LoadBalancer Service に払い出す IP pool と、worker 2 台から BGR 2 台へ IPv4／IPv6 の Service 経路を広報する BGP 設定を追加する。通常の LB 広報は IPv4 `/26`・IPv6 `/112` に集約し、集約 blackhole route と保守時の planned-shut profile も追加。BGP は各クラスタ 8 session Established。Cluster Mesh API の固定 VIP Service と、DCI 向けの個別 VIP 広報も追加する | [resources/10-lb-ipam.yaml](resources/10-lb-ipam.yaml)、[resources/20-bgp.yaml](resources/20-bgp.yaml)、[resources/21-bgp-planned-shut.yaml](resources/21-bgp-planned-shut.yaml)。集約 route は [configure-bgp-aggregate-blackhole.sh](../../../../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh)。Mesh Service は [resources/30-clustermesh-apiserver-service.yaml](resources/30-clustermesh-apiserver-service.yaml) |
| CoreDNS | kind の初期設定。選定 upstream の適用は未実施 | Pod から Docker 組み込み DNS へ到達できない場合の名前解決失敗を避けるため、CoreDNS の `forward .` を Pod から到達可能な IPv4 DNS resolver に変更する（`COREDNS_UPSTREAM_DNS` で指定） | 固定 manifest はなし。[configure-coredns-upstream.sh](../../../../scripts/cilium-lab/configure-coredns-upstream.sh) が `kube-system/coredns` ConfigMap の `data.Corefile` を変更。選定値は本ディレクトリの `runtime/20-coredns-upstream.env` に保存（Git 管理外） |
| Tetragon | 未導入 | `v1.7.0`、observe-only でイベントを観測する | [../tetragon/values/00-observe-only.yaml](../tetragon/values/00-observe-only.yaml) を別 Helm release として適用 |
| Egress／発展機能 | Egress Gateway／MCS API／WireGuard／Tetragon enforcement 無効 | 初期から変更なし | 標準の multisite-final では Egress 初期化も追加しない |
| 試験用リソース | 試験 workload／Policy／保守 label なし | 初期から変更なし | B では追加しない。A で試験した場合だけ一時追加し、終了後に撤去。Cluster Mesh API Service・CA・常設 BGP は保持する |
| [checksum 回避策](../../../../docs/cilium-lab/runbooks/checksum-compat-operations.md) | 未登録・未適用 | single-site で再現した Node 間 IPv6 LB の TCP checksum 不正に対する暫定策。multisite でも適用条件を確認し、必要なクラスタの両 worker に TX checksum off と 30 秒周期監視を設定する<br>※ **参考条件：single-site では 実行ホスト kernel `5.14.0-611.27.1.el9_7.x86_64` ＋ Cilium `v1.20.1` ＋ VXLAN／dual-stack／LB SNAT の検証済み構成で必要性を確認済み。** kind はホスト kernel を共有する。multisite では同じ版でも適用条件を別途確認し、別 kernel／Cilium も [helper 対応と実通信で判定](../../../../docs/cilium-lab/runbooks/kernel-compatibility-policy.md)する。 | [multisite の初回登録・監視・再適用手順](../../../../docs/cilium-lab/runbooks/checksum-compat-multisite.md)。初回登録・timer 作成後、一括 driver にクラスタごとの state を渡す |

WireGuard 試験時は両クラスタの暗号化条件を揃え、Cilium MTU を `9145` へ変更する。
Node Fabric `9150` と Pod 経路 `9000` を維持する設計であり、有効化までは `MTU: 9050` とする。
構築状況と実測結果は [検証ステータス](../../../../docs/cilium-lab/status.md) を参照する。

### values ファイル単体と、実際に適用される値の違い

`00-base.yaml` 単体の値は、初回導入の完成値ではない。初回・最終とも
`00-base.yaml` → `10-observability.yaml` → `20-multisite-clustermesh.yaml` → 生成 API values の順で重ねる。

| パラメータ | `00-base.yaml` 単体 | overlay 適用後：初回・最終とも同じ |
|---|---|---|
| `clustermesh.useAPIServer` | `false` | `true` |
| `clustermesh.config.enabled` | `false` | `true` |
| `clustermesh.cacheTTL` | `0s` | `10m` |
| `egressGateway.enabled`／`ciliumEndpointSlice.enabled` | ともに `false` | ともに `false` |
| `bpf.masquerade` | `false` | `false` |
| `MTU` | `9050` | `9050`。WireGuard 有効化時だけ `9145` に変更する設計 |

Cluster Mesh は初回から有効にする。API の起動と、固定 VIP・経路・CA を揃えた両クラスタの接続完了は別の段階である。
相手サイトの導入前は `cilium status` に remote cluster error が出るため、基盤の導入待ちは上記 resource の rollout で判定し、Mesh 接続は両サイト完成後に確認する。

接続先は `values/20-multisite-clustermesh.yaml` の `clustermesh.config.clusters[].ips` に固定 IPv4／IPv6 VIP を指定する。
Cilium 内部の host alias で `<cluster>.mesh.cilium.io` を解決し、共通 CA と FQDN の証明書検証を使用する。
通常の Pod／ホストの DNS に同名のレコードが追加されるわけではない。
API は worker 2 台への required anti-affinity に合わせ、`updateStrategy` を `maxSurge: 0`／`maxUnavailable: 1` とし、1 Pod ずつ更新する。

## 構築パターンの選択

| パターン | 用途 | 進め方 |
|---|---|---|
| [A：段階導入と個別試験](#staged-install) | 各クラスタ・機能を確認しながら構築する | 共通準備 → k02 個別導入 → CA 共有 → k03 個別導入 → 必要な個別試験 |
| [B：最終構成を最初から導入](#direct-final-install) | 個別試験を行わず両クラスタの常設基盤を揃える | 共通準備・適用条件確認 → 両クラスタの一括導入 → 最終状態確認 |

[共通準備](#multisite-preparation) と Node／Fabric の前提を確認してから、A または B を選ぶ。
B のコマンドは **k02 と k03 の両方**を変更するため、どちらか一方の README から 1 回実行する。
「全ての設定」は上表の常設基盤を指し、試験アプリや標準では無効な Egress Gateway は含めない。
試験した環境を戻す場合だけ [試験後の撤去・復元](#multisite-final-convergence) を使用する。
B でも導入時の readiness・DNS・Mesh 接続は確認する。性能・障害・全体通信試験は別途実施する。

<a id="multisite-preparation"></a>

## 共通の作業環境・CLI・chart・kubeconfig

実行ホストのリポジトリ内から設定する。Git 管理していない配置先では `REPO_ROOT` を実際の絶対パスに置き換える。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export SITE_TYPE="multisite"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_${SITE_TYPE}"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
export KUBECONFIG_K02="${LAB_ROOT}/clab-nxos-fabric-multisite/adc-k02/k8s_kind/k02/kubeconfig-k02"
export KUBECONFIG_K03="${LAB_ROOT}/clab-nxos-fabric-multisite/bdc-k03/k8s_kind/k03/kubeconfig-k03"
export KUBECONFIG="${KUBECONFIG_K02}:${KUBECONFIG_K03}"
export KUBE_CONTEXT_K02="kind-adc-k02"
export KUBE_CONTEXT_K03="kind-bdc-k03"
export KUBE_CONTEXT="${KUBE_CONTEXT_K02}"
cd "${LAB_ROOT}"

../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client --check
command -v kubectl cilium hubble helm
kubectl version --client
cilium version --client
hubble version
helm version --short

test -r "${KUBECONFIG_K02}"
test -r "${KUBECONFIG_K03}"
kubectl config get-contexts "${KUBE_CONTEXT_K02}"
kubectl config get-contexts "${KUBE_CONTEXT_K03}"
kubectl --context "${KUBE_CONTEXT}" get nodes -o wide
```

初回は 3 Node が取得できれば Cilium 導入前の `NotReady` は許容する。
生成 kubeconfig は管理 API 用で、Fabric client 用 `runtime/kubeconfig/config` と用途を分ける。
読み取り権限は構築ユーザーに限定して用意し、single-site の同名 context を混在させない。

## Node／Fabric と互換性の前提

[Fabric の構築](../../../README.md) を先に完了し、Leaf L2／Fabric MTU `9216` と LACP を確認する。
`adc-k02` の eth1／eth2／bond／VLAN は MTU `9150`、管理 eth0 は `1500`、VLAN は `bond0.14`／`bond0.104` を使用する。
InternalIP は control-plane `172.16.4.11`、worker `172.16.4.21`、worker2 `172.16.4.22` と
対応する `fd21:0:0:4::1:1`／`fd21:0:0:4::2:1`／`fd21:0:0:4::2:2` で、topology の post-link 設定により構成する。
一括 driver は NIC／LACP／MTU や kubelet Node IP を修正しない。

```bash
../scripts/cilium-lab/preflight-host-and-kind.sh --host-only
for node in adc-k02-control-plane adc-k02-worker adc-k02-worker2; do
  printf '\nnode=%s\n' "$node"
  docker exec "$node" ip -o link show
  docker exec "$node" ip -br address
  docker exec "$node" cat /proc/net/bonding/bond0
  docker exec "$node" cat /var/lib/kubelet/kubeadm-flags.env
done
```

現行 kernel の回避策は [multisite 専用手順](../../../../docs/cilium-lab/runbooks/checksum-compat-multisite.md) で適用条件を確認する。
state と timer は新しい k02／k03 の cluster UID ごとに分離し、single-site の登録を流用しない。
一括 driver は `--checksum-state-k02`／`--checksum-state-k03` に対応し、Cilium 導入直後・DNS 設定前に
指定したクラスタの回避策を再適用・確認する。初回登録と timer 作成は別途実施する。
kernel 更新は multisite 試験後に検討する。実通信の受入範囲は [検証ステータス](../../../../docs/cilium-lab/status.md) で管理する。

## ファイル

| Path | 管理 | 用途 |
|---|---|---|
| `values/00-base.yaml` | Git | CNI、datapath、LB IPAM／BGP feature gate の固定設計値 |
| `values/10-observability.yaml` | Git | Hubble Agent／Relay／UI、TLS、dynamic metrics |
| `values/20-multisite-clustermesh.yaml` | Git | Cluster Mesh API、VIP、DNS、TLS |
| `resources/10-lb-ipam.yaml` | Git | `infra`／`app` の dual-stack pool |
| `resources/20-bgp.yaml` | Git | worker 2 Node の BGP peer／advertisement／source address |
| `resources/21-bgp-planned-shut.yaml` | Git | Node label で切り替える graceful-shutdown community 付き BGP profile |
| `resources/30-clustermesh-apiserver-service.yaml` | Git | 固定 VIP の dual-stack Cluster Mesh API Service |
| `../tetragon/values/00-observe-only.yaml` | Git | Tetragon observe-only 初期 values |
| `runtime/10-k8s-api.yaml` | Git 管理外 | control-plane `eth0` から生成する API endpoint |
| `runtime/20-coredns-upstream.env` | Git 管理外 | 実行環境で選定した Pod 到達可能な CoreDNS upstream |

固定 values では、dual-stack Kubernetes IPAM、VXLAN、kube-proxy replacement、基準 MTU `9050`（IPv4 VXLAN の Pod 経路 MTU `9000`）、
multi-device、Fabric 側 NodePort address、BGP Control Plane、Hubble、Cluster Mesh API を初回から
有効化する。Cluster Mesh API は worker 2 Node に 1 Pod ずつ配置する 2 replica、PDB
`minAvailable: 1`、外部 Service `ClientIP` affinity で構築する。Egress Gateway、MCS API、試験アプリは
初期構築に含めない。

Cluster Mesh の構成根拠は [Cilium Cluster Mesh Setup](https://docs.cilium.io/en/stable/network/clustermesh/setup/) と
[Cilium Helm Reference](https://docs.cilium.io/en/stable/helm-values/) を参照する。

<a id="staged-install"></a>

## パターン A：段階導入と個別試験

k02 の本節を完了してから、k03 の本節で CA 共有と導入を行う。
固定 values は各コンポーネントの初回導入時から最終設計値を使用する。
両クラスタの導入後は [共通の最終状態確認](#final-state-check) を実施し、必要な試験を
[Cluster Mesh 受入設計](../../../../docs/cilium-lab/design/clustermesh-fabric-dci-and-acceptance.md) に沿って追加する。

worker 2 Node だけに BGP speaker label を付与し、preflight を通過してから install する。

```bash
../scripts/cilium-lab/configure-cilium-node-labels.sh --context kind-adc-k02 --apply
../scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster adc-k02 \
  --kube-context kind-adc-k02
```

### API endpoint values の生成

Kind Node と Fabric interface の作成後、Cilium を導入する前に実行する。

```bash
../scripts/cilium-lab/render-k8s-api-values.sh \
  --cluster adc-k02 \
  --output k8s_kind/k02/cilium/runtime/10-k8s-api.yaml
```

スクリプトは control-plane `eth0` の IPv4 address を取得し、全 k02 Node から API `/livez` を確認してから
`k8sServiceHost` と `k8sServicePort` を出力する。生成ファイルは commit しない。

### 静的 render

```bash
helm template cilium k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/cilium/values/00-base.yaml \
  --values k8s_kind/k02/cilium/values/10-observability.yaml \
  --values k8s_kind/k02/cilium/values/20-multisite-clustermesh.yaml \
  --values k8s_kind/k02/cilium/runtime/10-k8s-api.yaml \
  > /tmp/cilium-k02-rendered.yaml
```

### 導入

実行前に render 差分と現在の Helm release を確認し、ユーザーがクラスタへの適用を明示した後に実行する。

```bash
helm upgrade --install cilium k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/cilium/values/00-base.yaml \
  --values k8s_kind/k02/cilium/values/10-observability.yaml \
  --values k8s_kind/k02/cilium/values/20-multisite-clustermesh.yaml \
  --values k8s_kind/k02/cilium/runtime/10-k8s-api.yaml \
  --wait \
  --timeout 10m
```

### checksum 回避策の初回登録・監視

必要なクラスタでは、CoreDNS より先に [multisite 専用手順](../../../../docs/cilium-lab/runbooks/checksum-compat-multisite.md) の
環境変数・state の準備、対象クラスタの初回登録・再適用・timer 作成を完了する。
本節までで Cilium を導入済みなので、専用手順の bootstrap は繰り返さない。

### CoreDNS upstream の設定

CoreDNS upstream は環境依存のため、固定 manifest へ保存しない。`--upstream`、環境変数
`COREDNS_UPSTREAM_DNS`、host `/etc/resolv.conf` の非 loopback IPv4 nameserver の順で値を選択する。

```bash
../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env

../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env \
  --apply
```

自動検出値を使用できない環境では、`--upstream` または `COREDNS_UPSTREAM_DNS` で Pod から到達可能な
IPv4 resolver を指定する。スクリプトは変更前後の DNS test と失敗時 rollback を行い、選定値を Git 管理外の
runtime record に保存する。

Cilium が Ready になった後、pool／BGP resource を適用する。k03 の Cilium 有効化前に
`cilium-ca` をコピーするため、k02 の CA 生成完了を先に確認する。

```bash
kubectl --context kind-adc-k02 -n kube-system rollout status ds/cilium --timeout=5m
kubectl --context kind-adc-k02 -n kube-system rollout status deployment/clustermesh-apiserver --timeout=5m
../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh \
  --cluster adc-k02 --action apply
kubectl --context kind-adc-k02 apply \
  -f k8s_kind/k02/cilium/resources/10-lb-ipam.yaml \
  -f k8s_kind/k02/cilium/resources/20-bgp.yaml \
  -f k8s_kind/k02/cilium/resources/21-bgp-planned-shut.yaml \
  -f k8s_kind/k02/cilium/resources/30-clustermesh-apiserver-service.yaml
kubectl --context kind-adc-k02 -n kube-system get secret cilium-ca

helm upgrade --install tetragon k8s_kind/client/runtime/charts/tetragon-1.7.0.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/tetragon/values/00-observe-only.yaml \
  --wait \
  --timeout 10m

kubectl --context kind-adc-k02 -n kube-system rollout status daemonset/tetragon
kubectl --context kind-adc-k02 -n kube-system rollout status deployment/tetragon-operator
```

旧 MetalLB 用 `manifest/` は誤適用防止のため削除済みである。

<a id="direct-final-install"></a>

## パターン B：個別試験を行わず両クラスタを最終構成で導入

本節だけで、環境設定 → 再起動後の Node 確認 → Cilium／CA → 条件付き checksum 回避策 →
DNS／LB／BGP／Mesh／Tetragon → 最終確認まで進める。別ページへの移動は必須にしない。
「最終構成」は共存試験前の通常基盤であり、Egress Gateway は無効のままにする。
両クラスタを変更するため、k02／k03 のどちらか一方の手順から 1 回だけ実行する。
失敗したブロックの後へ進まず、原因を解消する。lab／kind の作成・破棄や NX-OS への設定投入は含めない。

### 1. 作業環境・ツール・変更前記録

Containerlab 実行ホストの Bash で、リポジトリ内から実行する。
Git 管理していない配置先では `REPO_ROOT` を実際の絶対パスへ置き換える。
DNS は両クラスタの Pod から使用する IPv4 resolver を入力する。既存クラスタでは現在の選定値を維持する。
異なる DNS が必要な場合は、両方を一律に変更せずパターン A で個別設定する。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_multisite"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
export KUBECONFIG_K02="${LAB_ROOT}/clab-nxos-fabric-multisite/adc-k02/k8s_kind/k02/kubeconfig-k02"
export KUBECONFIG_K03="${LAB_ROOT}/clab-nxos-fabric-multisite/bdc-k03/k8s_kind/k03/kubeconfig-k03"
export KUBECONFIG="${KUBECONFIG_K02}:${KUBECONFIG_K03}"
export KUBE_CONTEXT_K02=kind-adc-k02 KUBE_CONTEXT_K03=kind-bdc-k03
cd "${LAB_ROOT}"
umask 077
mkdir -p "${LAB_ROOT}/operations/cilium-lab/runtime"
export FINAL_DIR="$(mktemp -d "${LAB_ROOT}/operations/cilium-lab/runtime/install-final-XXXXXXXX")"
read -r -p '両クラスタで使用する DNS resolver IPv4: ' COREDNS_UPSTREAM_DNS
export COREDNS_UPSTREAM_DNS
```

以降の各ブロックは子 Bash で途中エラー時に停止する。記録先には現在の values を保存し、認証情報は画面へ出さない。

```bash
bash <<'BASH'
set -euo pipefail
: "${COREDNS_UPSTREAM_DNS:?DNS resolver を設定してください}"
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client --check
test -r "$KUBECONFIG_K02"
test -r "$KUBECONFIG_K03"
for context in "$KUBE_CONTEXT_K02" "$KUBE_CONTEXT_K03"; do
  kubectl --context "$context" --request-timeout=15s get nodes -o wide
  helm list --all --namespace kube-system --kube-context "$context"
  kubectl --context "$context" get nodes -o yaml > "$FINAL_DIR/$context-nodes-before.yaml"
  kubectl --context "$context" -n kube-system get cm coredns -o yaml > "$FINAL_DIR/$context-coredns-before.yaml"
  if helm status cilium -n kube-system --kube-context "$context" >/dev/null 2>&1; then
    helm get values cilium -n kube-system --kube-context "$context" -o yaml > "$FINAL_DIR/$context-cilium-before.yaml"
  fi
done
../scripts/cilium-lab/converge-cilium-lab.sh --profile multisite-final \
  --context-k02 "$KUBE_CONTEXT_K02" --context-k03 "$KUBE_CONTEXT_K03" \
  --output-dir "$FINAL_DIR/rendered"
BASH
```

ここまでの driver は offline render のみ。生成 directory 全体を `kubectl apply -f` しない。
既存の実験 values／Policy がある場合は先に変更内容を確認し、通常 values で黙って上書きしない。

### 2. 再起動・再作成後の Node 設定と Cilium／CA

Node が `Ready` でも InternalIP が管理側 `172.18.*` の場合がある。
期待する Fabric IPv4／IPv6 は下表の値。Leaf L2／Fabric MTU `9216`、Node 側 `9150`、LACP が前提である。

| Node | InternalIP IPv4 | InternalIP IPv6 | Fabric interface |
|---|---|---|---|
| `adc-k02-control-plane` | `172.16.4.11` | `fd21:0:0:4::1:1` | `bond0.14` |
| `adc-k02-worker` | `172.16.4.21` | `fd21:0:0:4::2:1` | `bond0.14` |
| `adc-k02-worker2` | `172.16.4.22` | `fd21:0:0:4::2:2` | `bond0.104` |
| `bdc-k03-control-plane` | `172.16.5.11` | `fd21:0:0:5::1:1` | `bond0.105` |
| `bdc-k03-worker` | `172.16.5.21` | `fd21:0:0:5::2:1` | `bond0.105` |
| `bdc-k03-worker2` | `172.16.5.22` | `fd21:0:0:5::2:2` | `bond0.105` |

まず現在値を確認する。preflight は Node 側を検査するもので、Leaf の実効 MTU／LACP の確認を代替しない。

BDC Leaf0101／0102 では次の表示を確認する。Po の MTU が正しくても、物理ポートが member でなければ完成ではない。
`Po14`～`Po16` が `SU`、`Ethernet1/4`～`1/6` が対応する Po の `P`、物理・Po の MTU が `9216` であることを確認する。
2026-09-25 の再構築後は Po のみ設定済みで member が欠落し、物理 MTU `1500` のため Pod exec が停止した。
Nexus の復旧投入はこのクラスタ導入ブロックに含めず、対象差分を確認してから行う。

```text
show port-channel summary
show interface ethernet1/4 | include MTU
show interface ethernet1/5 | include MTU
show interface ethernet1/6 | include MTU
show interface port-channel14 | include MTU
show interface port-channel15 | include MTU
show interface port-channel16 | include MTU
show vpc brief
```

```bash
bash <<'BASH'
set -euo pipefail
for cluster in adc-k02 bdc-k03; do
  for role in control-plane worker worker2; do
    node="$cluster-$role"
    printf '\nnode=%s\n' "$node"
    docker exec "$node" ip -br address
    docker exec "$node" ip -4 route show
    docker exec "$node" ip -6 route show
    docker exec "$node" cat /var/lib/kubelet/kubeadm-flags.env
  done
done
BASH
```

**InternalIP が異なる場合だけ**次のブロックで保存設計へ修正する。
helper は指定 IP が Node 上に存在することを確認し、引数が異なる Node の kubelet だけを再起動する。
既に正しい場合はこの修正ブロックを省略する。Fabric IP／bond 自体がない場合は先に Node ネットワークの復旧が必要である。

```bash
bash <<'BASH'
set -euo pipefail
while read -r node addresses context; do
  docker exec "$node" cat /var/lib/kubelet/kubeadm-flags.env > "$FINAL_DIR/$node-kubeadm-flags-before.env"
  docker exec -i -e KUBELET_NODE_IP="$addresses" "$node" bash -s \
    < ../scripts/cilium-lab/configure-kubelet-node-ip.sh
  kubectl --context "$context" wait --for="jsonpath={.status.addresses[0].address}=${addresses%%,*}" "node/$node" --timeout=90s
  kubectl --context "$context" wait --for=condition=Ready "node/$node" --timeout=90s
done <<'NODES'
adc-k02-control-plane 172.16.4.11,fd21:0:0:4::1:1 kind-adc-k02
adc-k02-worker 172.16.4.21,fd21:0:0:4::2:1 kind-adc-k02
adc-k02-worker2 172.16.4.22,fd21:0:0:4::2:2 kind-adc-k02
bdc-k03-control-plane 172.16.5.11,fd21:0:0:5::1:1 kind-bdc-k03
bdc-k03-worker 172.16.5.21,fd21:0:0:5::2:1 kind-bdc-k03
bdc-k03-worker2 172.16.5.22,fd21:0:0:5::2:2 kind-bdc-k03
NODES
BASH
```

続いて label と preflight を確認する。Node の経路欠落はここで止めて復旧する。
期待する Fabric 経路は k02 が `172.16.0.0/16 via 172.16.4.1` と `fd21:0:0::/48 via fd21:0:0:4::1`、
k03 が `172.16.0.0/16 via 172.16.5.1` と `fd21:0:0::/48 via fd21:0:0:5::1` である。

```bash
bash <<'BASH'
set -euo pipefail
for entry in 'adc-k02 kind-adc-k02' 'bdc-k03 kind-bdc-k03'; do
  read -r cluster context <<< "$entry"
  ../scripts/cilium-lab/configure-cilium-node-labels.sh --context "$context" --apply
  ../scripts/cilium-lab/preflight-host-and-kind.sh --cluster "$cluster" --kube-context "$context"
done
BASH
```

Cilium を k02 → CA 共有 → k03 の順に揃える。既存 CA が異なる場合は停止する。`--replace-existing` は使わない。
導入済みの場合も保存 values と現在値の差分を確認してから実行する。
この時点の全体 `cilium status --wait` は相手サイトの未完成を待ってしまうため使用しない。

```bash
bash <<'BASH'
set -euo pipefail
for site in k02 k03; do
  if [[ "$site" == k02 ]]; then
    cluster=adc-k02; context="$KUBE_CONTEXT_K02"
  else
    cluster=bdc-k03; context="$KUBE_CONTEXT_K03"
  fi
  ../scripts/cilium-lab/render-k8s-api-values.sh \
    --cluster "$cluster" --output "k8s_kind/$site/cilium/runtime/10-k8s-api.yaml"
  if [[ "$site" == k03 ]]; then
    ../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
      --source-context "$KUBE_CONTEXT_K02" --target-context "$KUBE_CONTEXT_K03" --apply
  fi
  helm upgrade --install cilium k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
    --namespace kube-system --kube-context "$context" \
    --values "k8s_kind/$site/cilium/values/00-base.yaml" \
    --values "k8s_kind/$site/cilium/values/10-observability.yaml" \
    --values "k8s_kind/$site/cilium/values/20-multisite-clustermesh.yaml" \
    --values "k8s_kind/$site/cilium/runtime/10-k8s-api.yaml" --wait --timeout 10m
  for resource in daemonset/cilium deployment/cilium-operator deployment/clustermesh-apiserver; do
    kubectl --context "$context" -n kube-system rollout status "$resource" --timeout=5m
  done
  kubectl --context "$context" get ciliumnodes \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.addresses}{"\n"}{end}'
done
BASH
```

kubelet 修正前に Cilium が導入済みの場合、Helm の再適用だけでは旧 IP が残ることがある。
CiliumNode の `InternalIP` が管理側のままのクラスタだけ、次を実行してから再照合する。

```bash
export REPAIR_CONTEXT=kind-adc-k02 # 必要なら kind-bdc-k03 に変更して同じ確認を行う
bash <<'BASH'
set -euo pipefail
kubectl --context "$REPAIR_CONTEXT" -n kube-system rollout restart daemonset/cilium
kubectl --context "$REPAIR_CONTEXT" -n kube-system rollout status daemonset/cilium --timeout=5m
kubectl --context "$REPAIR_CONTEXT" get ciliumnodes \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.addresses}{"\n"}{end}'
BASH
```

### 3. checksum 回避策の採否・必要な場合の登録

回避策は一律必須ではない。以前の clab02 の記録では対象 helper の IPv6 flag は未対応だったが、
試験した LB 経路に checksum 不正はなく、state／timer を作らず `on` を維持した。
現在の kernel／Cilium／経路も確認して判断し、未評価を「不要」と読み替えない。
復旧直後の未評価状態では、通常基盤の設定を先に揃えても試験開始可とはしない。
手順 5 の疎通・checksum 確認で不正が再現した場合は、本節へ戻って登録する。

```bash
for node in adc-k02-worker adc-k02-worker2 bdc-k03-worker bdc-k03-worker2; do
  docker exec "$node" uname -r
  docker exec "$node" ethtool -k cilium_vxlan
 done
export COMPAT_SCRIPT="${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/checksum-compat.py"
export K02_UID="$(kubectl --context "$KUBE_CONTEXT_K02" get namespace kube-system -o jsonpath='{.metadata.uid}')"
export K03_UID="$(kubectl --context "$KUBE_CONTEXT_K03" get namespace kube-system -o jsonpath='{.metadata.uid}')"
: "${K02_UID:?UID 取得失敗}" "${K03_UID:?UID 取得失敗}"
export COMPAT_STATE_K02="${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02/${K02_UID}/checksum-compat.json"
export COMPAT_STATE_K03="${LAB_ROOT}/operations/cilium-lab/runtime/bdc-k03/${K03_UID}/checksum-compat.json"
```

**必要と判断したクラスタだけ**以下を実行する。両方で必要なら `COMPAT_SITE` を変えて繰り返す。
既存 state は再登録せず照合する。UID／kernel／image 不一致を state の上書きで隠さない。

```bash
export COMPAT_SITE=k02 # k03 が必要な場合は k03
bash <<'BASH'
set -euo pipefail
case "$COMPAT_SITE" in
  k02) cluster=adc-k02; context="$KUBE_CONTEXT_K02"; config="$KUBECONFIG_K02"; state="$COMPAT_STATE_K02"; uid="$K02_UID" ;;
  k03) cluster=bdc-k03; context="$KUBE_CONTEXT_K03"; config="$KUBECONFIG_K03"; state="$COMPAT_STATE_K03"; uid="$K03_UID" ;;
  *) exit 1 ;;
esac
unit="cilium-checksum-multisite-$cluster-$uid"
if [[ ! -f "$state" ]]; then
  read -r -p '両 worker の変更前 tx-checksum-ip-generic (on/off): ' restore_tx < /dev/tty
  read -r -p '今回の適用根拠と証跡 ID: ' reason < /dev/tty
  python3 "$COMPAT_SCRIPT" enroll --state "$state" \
    --cluster "$cluster" --context "$context" --kubeconfig "$config" \
    --node "$cluster-worker" --node "$cluster-worker2" \
    --restore-tx "${restore_tx:?}" --reason "${reason:?}"
fi
python3 "$COMPAT_SCRIPT" reconcile --state "$state"
python3 "$COMPAT_SCRIPT" check --state "$state"
loginctl enable-linger "$(id -un)"
python3 ../scripts/cilium-lab/install-checksum-monitor.py \
  --state "$state" --runtime-bin "$K8S_CLIENT_RUNTIME/bin" --unit "$unit"
systemctl --user is-active "$unit.timer"
systemctl --user show "$unit.service" -p Result -p ExecMainStatus -p ExecMainStartTimestamp
BASH
```

両 worker の元の値が異なる場合は一括登録せず、復元方針を決める。
`enable-linger` はログアウト後・ホスト起動後も user timer を動かす設定である。
当該クラスタの timer `active`、service `Result=success`／`ExecMainStatus=0` を確認する。

### 4. 両クラスタの常設設定を一括導入

登録済み state があるクラスタだけ driver に渡す。回避策なしの初回構築でも、このコマンドを使用できる。
既存 timer があるのに対応 state が見つからない場合は、その所属と現在の UID を解決してから進む。

```bash
bash <<'BASH'
set -euo pipefail
checksum_args=()
[[ ! -f "$COMPAT_STATE_K02" ]] || checksum_args+=(--checksum-state-k02 "$COMPAT_STATE_K02")
[[ ! -f "$COMPAT_STATE_K03" ]] || checksum_args+=(--checksum-state-k03 "$COMPAT_STATE_K03")
../scripts/cilium-lab/converge-cilium-lab.sh --profile multisite-final \
  --context-k02 "$KUBE_CONTEXT_K02" --context-k03 "$KUBE_CONTEXT_K03" \
  "${checksum_args[@]}" \
  --coredns-upstream "${COREDNS_UPSTREAM_DNS:?DNS resolver を設定してください}" \
  --output-dir "$FINAL_DIR/applied-render" --apply
BASH
```

driver は Cilium、条件付き checksum、CoreDNS、LB pool、BGP、Mesh API Service、Tetragon を順に適用する。
導入途中は各コンポーネントの rollout で判断し、両サイト完成後に Cilium 全体・Mesh 接続を確認する。
失敗時に全設定を自動 rollback する処理ではない。Node／NX-OS の作成・修正、試験 workload、Egress 有効化は行わない。

### 5. 試験前の完成状態を確認

```bash
bash <<'BASH'
set -euo pipefail
for context in "$KUBE_CONTEXT_K02" "$KUBE_CONTEXT_K03"; do
  kubectl --context "$context" get nodes -o wide -L bgp-speaker,bgp-maintenance
  cilium status --context "$context"
  cilium bgp peers --context "$context"
  cilium clustermesh status --context "$context"
  hubble status --kube-context "$context" -P
  kubectl --context "$context" -n kube-system get \
    daemonset/cilium daemonset/tetragon deployment/tetragon-operator \
    deployment/hubble-relay deployment/clustermesh-apiserver \
    service/clustermesh-apiserver poddisruptionbudget/clustermesh-apiserver
  helm get values cilium --kube-context "$context" -n kube-system -o json | \
    python3 -c 'import json,sys; v=json.load(sys.stdin); print("egressGateway:", v.get("egressGateway"), "ciliumEndpointSlice:", v.get("ciliumEndpointSlice"))'
  helm get values cilium --kube-context "$context" -n kube-system -o yaml > "$FINAL_DIR/$context-cilium-after.yaml"
done
../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
  --source-context "$KUBE_CONTEXT_K02" --target-context "$KUBE_CONTEXT_K03"
BASH
```

期待値は両クラスタ 3 Node Ready、Cilium／Tetragon 各 `3/3`、Mesh API 各 `2/2`、BGP 各 `8/8 Established`、
Mesh agent `3/3`・KVStoreMesh `2/2` connected。Mesh API VIP は k02 `172.16.14.10`／`fd21:0:0:14:0:0:1:10`、
k03 `172.16.15.10`／`fd21:0:0:15:0:0:1:10`、Service affinity `ClientIP`、PDB `minAvailable: 1`。
Egress Gateway は `false`、MCS／WireGuard も無効である。

この節は個別の通信・障害試験を省略する導入手順であり、Ready の確認を共存試験の開始条件の合格とはしない。
両 AF の実通信、初回 ARP／ND、checksum、MTU、Global Service／Policy、障害・復帰は別に受け入れる。
次は [先行試験順序](../../../../docs/cilium-lab/design/clustermesh-cluster-upgrade-design.md#upgrade-prerequisites) に沿って残受入を確認し、
[Egress Gateway／Mesh 共存試験](../../../../docs/cilium-lab/tests/egress-clustermesh-coexistence-test.md)へ進む。

<a id="multisite-final-convergence"></a>

## 補足：試験後の撤去・最終構成への復元

試験設定が入っている既存クラスタ向けの手順である。新規構築では A または B を使用する。

### 1. 試験用設定を撤去し、常設基盤を保持する

試験の通信・capture・外部専用サーバ・port-forward を、それぞれの実施セッションの終了手順で停止する。
Node の一時停止、cordon、BGP 保守 label、Tetragon の一時停止 selector は、その試験で変更した対象だけを元に戻す。
BGP の通常状態は `bgp-maintenance` label が存在しない状態であり、値を `normal` にする方式ではない。

Cluster Mesh demo を終了する場合は、`cilium-test` が今回の demo 専用であることを両クラスタで確認してから撤去する。
以下の Kustomize には namespace の削除も含まれるため、別の workload を追加している場合は対象を整理してから実施する。

```bash
kubectl --context "${KUBE_CONTEXT_K02}" delete -k \
  k8s_kind/k02/cilium/manifests/validation/clustermesh-demo --ignore-not-found
kubectl --context "${KUBE_CONTEXT_K03}" delete -k \
  k8s_kind/k03/cilium/manifests/validation/clustermesh-demo --ignore-not-found
```

その他の NP／TG／CLI 試験は、実行時に使用した専用 namespace／Policy を確認して撤去する。
Cluster Mesh API の Service、CA Secret、LB pool、通常／planned-shut BGP、Tetragon 本体は保持する。
Egress／Cluster Mesh 併用は標準構成と別の実験であり、実施した場合は
[併用試験の rollback](../../../../docs/cilium-lab/tests/egress-clustermesh-coexistence-test.md) で実験用 Policy・広報・IP・values を戻してから進む。
single-site の Egress 初期化 DaemonSet を本手順で追加しない。

### 2. 入力と変更前状態を確認する

両 kubeconfig と CLI／chart cache を共通準備のとおり設定する。
[multisite 専用手順](../../../../docs/cilium-lab/runbooks/checksum-compat-multisite.md) の環境変数を設定し、現在の UID の `COMPAT_STATE_K02`／`COMPAT_STATE_K03` と
各 timer が登録済みであることを確認する。state を作り直して不一致を隠さない。
各確認で失敗した場合は後続へ進まず、原因を解消してから再開する。
既存クラスタの CA が一致することを、設定変更を始める前に確認する。

```bash
../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
  --source-context "${KUBE_CONTEXT_K02}" --target-context "${KUBE_CONTEXT_K03}"
umask 077
mkdir -p "${LAB_ROOT}/operations/cilium-lab/runtime"
export FINAL_DIR="$(mktemp -d "${LAB_ROOT}/operations/cilium-lab/runtime/finalize-XXXXXXXX")"
for context in "${KUBE_CONTEXT_K02}" "${KUBE_CONTEXT_K03}"; do
  helm get values cilium --kube-context "$context" -n kube-system -o yaml \
    > "${FINAL_DIR}/${context}-cilium-before.yaml"
  helm get values tetragon --kube-context "$context" -n kube-system -o yaml \
    > "${FINAL_DIR}/${context}-tetragon-before.yaml"
  kubectl --context "$context" get nodes -o yaml > "${FINAL_DIR}/${context}-nodes-before.yaml"
  kubectl --context "$context" -n kube-system get configmap coredns -o yaml \
    > "${FINAL_DIR}/${context}-coredns-before.yaml"
done
```

CoreDNS の保存値はクラスタごとに確認する。一括 driver の `--coredns-upstream` は両クラスタで共通となる。
以下は保存済みの DNS が同一で、両クラスタの Pod から到達確認済みの場合に使用する。
値が異なる場合は一括適用へ進まず、各 README の個別導入・CoreDNS 手順でそれぞれの値を維持する。

```bash
DNS_K02="$(awk -F= '$1 == "COREDNS_UPSTREAM_DNS" {print $2}' k8s_kind/k02/cilium/runtime/20-coredns-upstream.env)"
DNS_K03="$(awk -F= '$1 == "COREDNS_UPSTREAM_DNS" {print $2}' k8s_kind/k03/cilium/runtime/20-coredns-upstream.env)"
: "${DNS_K02:?k02 の選定済み DNS が必要です}" "${DNS_K03:?k03 の選定済み DNS が必要です}"
unset COREDNS_UPSTREAM_DNS
if [[ "$DNS_K02" = "$DNS_K03" ]]; then
  export COREDNS_UPSTREAM_DNS="$DNS_K02"
else
  printf '両クラスタの DNS が異なるため、一括適用を停止して個別手順を使用してください。\n' >&2
fi
```

### 3. Offline render と一括適用

まず `--apply` なしで静的 render を行う。出力は仮の API address と試験用 manifest も含むため、
その directory 全体を `kubectl apply -f` しない。保存 values と生成結果の差分を確認する。

```bash
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client --check
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile multisite-final \
  --context-k02 "${KUBE_CONTEXT_K02}" --context-k03 "${KUBE_CONTEXT_K03}" \
  --output-dir "${FINAL_DIR}/rendered"
```

checksum など前提に残る事項を解消し、両クラスタへの反映を行う段階で実行する。
この操作は Helm upgrade と DNS／BGP／Cluster Mesh／Tetragon の適用を含む。

```bash
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile multisite-final \
  --context-k02 "${KUBE_CONTEXT_K02}" --context-k03 "${KUBE_CONTEXT_K03}" \
  --checksum-state-k02 "${COMPAT_STATE_K02:?k02 の初回登録を完了してください}" \
  --checksum-state-k03 "${COMPAT_STATE_K03:?k03 の初回登録を完了してください}" \
  --coredns-upstream "${COREDNS_UPSTREAM_DNS:?両クラスタで共通の DNS を確認してください}" \
  --output-dir "${FINAL_DIR}/applied-render" \
  --apply
```

処理順は両 state の所属・UID 照合 → k02 の準備・Cilium・checksum・DNS・LB／BGP／Mesh API Service → k03 の準備・CA 照合／共有 →
k03 の Cilium・checksum・DNS・LB／BGP／Mesh API Service → 両 Tetragon → readiness／Mesh 状態確認。
既存 CA が異なる場合は停止し、通常手順で `--replace-existing` を使用しない。
途中失敗時は後続へ進まないが、自動で全設定を rollback する処理ではない。
NIC／MTU／NX-OS、試験用リソースの削除、Egress 初期化、checksum の初回登録・timer 作成は一括 driver の適用対象外である。

[共通の最終状態確認](#final-state-check) へ進む。

<a id="final-state-check"></a>

## 共通：最終状態の確認

checksum を使用したクラスタは [専用手順の最終確認](../../../../docs/cilium-lab/runbooks/checksum-compat-multisite.md#7-最終確認と解除再構築) で
state の `check`、timer active、service 成功を確認する。

A で個別導入した場合も、以下で保存先を準備する。B／試験後の復元では既に設定した `FINAL_DIR` を使用する。

```bash
if [[ -z "${FINAL_DIR:-}" ]]; then
  umask 077
  mkdir -p "${LAB_ROOT}/operations/cilium-lab/runtime"
  export FINAL_DIR="$(mktemp -d "${LAB_ROOT}/operations/cilium-lab/runtime/verify-final-XXXXXXXX")"
fi
```

```bash
for context in "${KUBE_CONTEXT_K02}" "${KUBE_CONTEXT_K03}"; do
  kubectl --context "$context" get nodes -o wide -L bgp-speaker,bgp-maintenance
  cilium status --context "$context"
  cilium bgp peers --context "$context"
  cilium clustermesh status --context "$context"
  hubble status --kube-context "$context" -P
  kubectl --context "$context" -n kube-system get \
    daemonset/cilium daemonset/tetragon deployment/tetragon-operator \
    deployment/hubble-relay deployment/clustermesh-apiserver \
    service/clustermesh-apiserver poddisruptionbudget/clustermesh-apiserver
  helm get values cilium --kube-context "$context" -n kube-system -o yaml \
    > "${FINAL_DIR}/${context}-cilium-after.yaml"
done
../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
  --source-context "${KUBE_CONTEXT_K02}" --target-context "${KUBE_CONTEXT_K03}"
```

各クラスタ Node 3 台、Cilium／Tetragon 各 3 台、Mesh API 2 replica、BGP 各 8 session を確認する。
Mesh API VIP は k02 `172.16.14.10`／`fd21:0:0:14:0:0:1:10`、
k03 `172.16.15.10`／`fd21:0:0:15:0:0:1:10`、Service affinity は `ClientIP`、PDB は `minAvailable: 1` が期待値。
Node／Fabric MTU、Pod 経路 `9000`、DCI の経路広告・IPv4／IPv6 の実通信は別途実測する。
readiness／Mesh 接続の成功だけを全機能・性能・障害復旧の合格とは扱わない。

操作環境と UI は [multisite README](../../../README.md#multisite-client-environment)、
受入範囲は [Cluster Mesh 設計](../../../../docs/cilium-lab/design/clustermesh-fabric-dci-and-acceptance.md) を参照する。
一括適用・初期化・通信確認の実測結果は [検証ステータス](../../../../docs/cilium-lab/status.md) を参照する。新規構築時はゼロからの適用を確認し、
Node 再起動後のリンク復旧・設定維持は別の未検証事項として残す。
