# adc-k02 Cilium 構築：段階導入と最終構成の一括導入

この README は、single-site `adc-k02` を段階的に導入して試験する方法と、
個別試験を行わず現在の最終構成を最初から導入する方法をまとめる。
設定値は保存済み Helm values・manifest・共通 helper を使用する。

## 最初に確認：初期導入と最終構成の差分

ここで「初期」は、パターン A の **Cilium の初回 Helm install 直後**を指す。
「最終」は、checksum など必要な初期化と全常設コンポーネントの導入を完了した状態を指す。
**A の基盤構築完了時と B の完了時は同じ設定になる。** 試験の実施を理由に MTU や機能フラグを切り替える構成ではない。
以下は保存済み設定と導入手順の比較であり、稼働環境を今回再確認した結果ではない。


どちらの構築パターンも、下表の常設基盤を最終状態とする。
「全ての設定」はこの基盤を指し、試験専用 workload／Policy や未採用の発展機能は含めない。
試験する場合だけ専用設定を追加し、終了後に同じ基盤へ戻す。`singlesite-final` は常設基盤の適用 profile であり、
全試験の合格を示す名前ではない。現在の全体 connectivity と性能受入は未完了である。

| 対象 | 初期：Cilium 導入直後 | 最終：常設基盤の完成時 | 差分・適用タイミング／設定元 |
|---|---|---|---|
| Leaf／Fabric | L2／Fabric MTU `9216`、LACP 設定済みが前提 | 初期から変更なし | Cilium 導入前に構築・確認。一括 driver では変更しない |
| Node Fabric | eth1／eth2／bond／VLAN は MTU `9150`、管理 eth0 は `1500`。InternalIP と Cilium VXLAN 終端は Fabric IP | 初期から変更なし | Cilium 導入前の前提。topology の post-link 設定。下記の前提確認 |
| Cilium | `v1.20.1`、dual-stack、IPv4 VXLAN、kube-proxy replacement、基準 MTU `9050`、Pod 経路 MTU `9000` | 初期から変更なし | 初回から最終 values を使用。`values/00-base.yaml` と生成 API values |
| API bootstrap | control-plane の管理 eth0 IPv4、TCP `6443` | 初期から変更なし | 方式は同じ。再構築時は現在の API address を再生成。`render-k8s-api-values.sh` |
| Hubble | Agent／Relay／UI・TLS・dynamic metrics 有効 | 初期から変更なし | Cilium と同時に導入。`values/10-observability.yaml` |
| Egress feature | BPF masquerading／Egress Gateway 有効、CES 無効 | 初期から変更なし | 初回から `20-singlesite-egress.yaml` を重ねる。`values/20-singlesite-egress.yaml` |
| Egress IP | 未設定 | Egress IP を持つ `egress0` を対象の各 worker Node へ設定する。worker：`172.16.24.1/32`／`fd21:0:0:24::1/128`、worker2：`172.16.24.2/32`／`fd21:0:0:24::2/128`。DaemonSet・ConfigMap・対象 label を保持 | IP 定義：[manifests/egress-interface-init/configmap.yaml](manifests/egress-interface-init/configmap.yaml) の `nodes.json`。初期化処理：[daemonset.yaml](manifests/egress-interface-init/daemonset.yaml)。適用単位：[kustomization.yaml](manifests/egress-interface-init/kustomization.yaml) |
| CoreDNS | kind の初期設定。選定 upstream の適用は未実施 | Pod から Docker 組み込み DNS へ到達できない場合の名前解決失敗を避けるため、CoreDNS の `forward .` を Pod から到達可能な IPv4 DNS resolver に変更する（`COREDNS_UPSTREAM_DNS` で指定） | 固定 manifest はなし。[configure-coredns-upstream.sh](../../../../scripts/cilium-lab/configure-coredns-upstream.sh) が `kube-system/coredns` ConfigMap の `data.Corefile` を変更。選定値は本ディレクトリの `runtime/20-coredns-upstream.env` に保存（Git 管理外） |
| LB／BGP | BGP feature と worker speaker label は有効。LB pool／BGP CR／集約 route は未適用 | LoadBalancer Service に払い出す IP pool と、worker 2 台から BGR 2 台へ IPv4／IPv6 の Service 経路を広報する BGP 設定を追加する。通常の LB 広報は IPv4 `/26`・IPv6 `/112` に集約し、集約 blackhole route と保守時の planned-shut profile も追加。BGP は各クラスタ 8 session Established | [resources/10-lb-ipam.yaml](resources/10-lb-ipam.yaml)、[resources/20-bgp.yaml](resources/20-bgp.yaml)、[resources/21-bgp-planned-shut.yaml](resources/21-bgp-planned-shut.yaml)。集約 route は [configure-bgp-aggregate-blackhole.sh](../../../../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh) |
| Tetragon | 未導入 | `v1.7.0`、observe-only。試験用 TracingPolicy は撤去 | 後続で別 Helm release として追加。observe-only のまま。`../tetragon/values/00-observe-only.yaml` |
| [checksum 回避策](../../../../docs/cilium-lab/runbooks/checksum-compat-operations.md) | 未登録・未適用。元の offload 値は実環境で確認する | 現行 kernel 構成で再現した Node 間 IPv6 LB の TCP checksum 不正を回避するため、両 worker の `cilium_vxlan` の `tx-checksum-ip-generic` を `off` にし、30 秒周期で状態を監視する<br>※ **適用条件：実行ホスト kernel `5.14.0-611.27.1.el9_7.x86_64` ＋ Cilium `v1.20.1` ＋ VXLAN／dual-stack／LB SNAT の検証済み構成では必要。** kind はホスト kernel を共有する。別 kernel／Cilium では版番号だけで要否を決めず、[helper 対応と実通信で判定](../../../../docs/cilium-lab/runbooks/kernel-compatibility-policy.md)する。 | [原因・適用条件・運用手順](../../../../docs/cilium-lab/runbooks/checksum-compat-operations.md)。適用は [checksum-compat.py](../../../../scripts/cilium-lab/checksum-compat.py)、監視 unit の作成は [install-checksum-monitor.py](../../../../scripts/cilium-lab/install-checksum-monitor.py) |
| 試験用リソース | なし | 初期から変更なし（lab-smoke を疎通確認用に保持する場合を除く） | B では追加しない。A で追加した Egress Policy・Egress 広報・NP／TG 専用 namespace・外部試験サーバは終了後に撤去。下記の試験後の撤去手順 |
| 発展機能 | Cluster Mesh／WireGuard／Tetragon enforcement 無効 | 初期から変更なし | 将来の WireGuard 試験時のみ MTU を変更。WireGuard 試験時だけ Cilium MTU を `9145` へ変更し、Node `9150` と Pod 経路 `9000` を維持する |

### values ファイル単体と、実際に適用される値の違い

`00-base.yaml` 単体の値は、初回導入の完成値ではない。初回・最終とも
`00-base.yaml` → `10-observability.yaml` → `20-singlesite-egress.yaml` → 生成 API values の順で重ねる。

| パラメータ | `00-base.yaml` 単体 | overlay 適用後：初回・最終とも同じ |
|---|---|---|
| `bpf.masquerade` | `false` | `true` |
| `egressGateway.enabled` | `false` | `true` |
| `ciliumEndpointSlice.enabled` | `false` | `false` |
| `MTU` | `9050` | `9050`。WireGuard 有効化時だけ `9145` に変更する設計 |

Egress Gateway の機能有効化、`egress0`／IP の作成、通信に適用する Egress Policy／経路広報は別の設定である。
最終基盤は前二者までを含む。Egress Policy／専用広報は試験時だけ追加する。


## 構築パターンの選択

| パターン | 用途 | 進め方 |
|---|---|---|
| [A：段階導入と個別試験](#staged-install) | 各設定の役割・動作を確認しながら構築する | 共通準備 → 各コンポーネントを順に導入 → 初期受入 → 必要な個別試験 |
| [B：最終構成を最初から導入](#direct-final-install) | 個別試験を行わず常設基盤を揃える | 共通準備 → Cilium と checksum の初回準備 → 常設設定の一括適用 → 最終状態確認 |

まず [共通の作業環境](#working-environment)、[Node／Fabric の前提](#fabric-prerequisites)、
以下の CLI・chart・kubeconfig 準備を完了する。A と B は選択式であり、両方を順に実行する必要はない。
試験した環境を戻す場合だけ、補足の [試験後の撤去・復元](#final-convergence) を使用する。
B でも導入時の readiness・DNS・設定整合は確認する。connectivity 全体試験・性能・障害試験は別途実施する。

Containerlab／kind と Leaf／BGR の初期構築は [single-site 構築手順](../../../README.md) を先に完了する。
本書の一括適用 driver は Node の作成、Fabric NIC／LACP／MTU の修正、NX-OS config 投入・保存を実行しない。
Leaf の最新 MTU／LACP 変更の startup-config 保存は未実施事項として残る。

<a id="working-environment"></a>

## 共通の作業環境

Containerlab 実行ホストの Bash で、このリポジトリ内から実行する。
Git 管理していない実行ホストでは `REPO_ROOT` を実際のリポジトリ絶対パスに置き換える。
以降の相対パスは `nxos_fabric/nxos_singlesite` を基準とする。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_singlesite"
export KUBE_CONTEXT="kind-adc-k02"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export KUBECONFIG="${LAB_ROOT}/clab-nxos-fabric-singlesite/adc-k02/k8s_kind/k02/kubeconfig-k02"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
cd "${LAB_ROOT}"

export COMPAT_SCRIPT="${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/checksum-compat.py"
export COMPAT_STATE="${COMPAT_STATE:-${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02/checksum-compat.json}"
```

`COMPAT_STATE` は実行ホストの登録済みファイルを使用する。既存 timer が別パスを参照している場合は、
そのパスを指定する。新規クラスタに以前の cluster UID の state を流用しない。
各コマンドが失敗した場合は後続へ進まず、表示された差分・原因を確認する。

<a id="fabric-prerequisites"></a>

## Node／Fabric の前提確認

Leaf の対象 L2 ポート・Fabric の MTU は `9216`、LACP は両 member が参加していることを確認する。
Node の設定は topology の post-link 処理で作成する。Cilium 導入前後とも、次の値を基準とする。

| Node | Fabric interface | InternalIP IPv4／IPv6 |
|---|---|---|
| `adc-k02-control-plane` | `bond0.14` | `172.16.4.11`／`fd21:0:0:4::1:1` |
| `adc-k02-worker` | `bond0.14` | `172.16.4.21`／`fd21:0:0:4::2:1` |
| `adc-k02-worker2` | `bond0.104` | `172.16.4.22`／`fd21:0:0:4::2:2` |

```bash
for node in adc-k02-control-plane adc-k02-worker adc-k02-worker2; do
  printf '\nnode=%s\n' "$node"
  docker exec "$node" ip -o link show
  docker exec "$node" ip -br address
  docker exec "$node" cat /proc/net/bonding/bond0
  docker exec "$node" cat /var/lib/kubelet/kubeadm-flags.env
done
```

eth1／eth2／bond0／上表の VLAN の MTU `9150`、eth0 の MTU `1500`、両 LACP member の up と
同一 aggregator への参加、kubelet の `--node-ip` が上表と一致することを確認する。
差分がある場合は、保存済み topology の反映を先に完了してから Cilium の適用へ進む。
稼働後に Node IP を変更した場合は Cilium の終端と既存 hostNetwork 試験用 Pod の IP も照合する。

## ファイル

| Path | 管理 | 用途 |
|---|---|---|
| `values/00-base.yaml` | Git | CNI、datapath、LB IPAM／BGP feature gate の固定設計値 |
| `values/10-observability.yaml` | Git | Hubble Agent／Relay／UI、TLS、dynamic metrics |
| `values/20-singlesite-egress.yaml` | Git | BPF masquerade と Egress Gateway feature gate |
| `resources/10-lb-ipam.yaml` | Git | `infra`／`app` の dual-stack pool |
| `resources/20-bgp.yaml` | Git | worker 2 Node の BGP peer／advertisement／source address |
| `resources/21-bgp-planned-shut.yaml` | Git | Node label で切り替える graceful-shutdown community 付き BGP profile |
| `manifests/egress-interface-init/` | Git | Egress Gateway Node の `egress0`／Egress IP を初期設定する ConfigMap と DaemonSet |
| `manifests/validation/` | Git | 初期構築と分離した smoke、Egress、Network Policy、Tetragon 試験 layer |
| `../tetragon/values/00-observe-only.yaml` | Git | Tetragon observe-only 初期 values |
| `../../client/chart-versions.env` | Git | Cilium／Tetragon Helm chart の固定 version |
| `../../client/runtime/charts/` | Git 管理外 | 検証済み Helm chart cache |
| `runtime/10-k8s-api.yaml` | Git 管理外 | control-plane `eth0` から生成する API endpoint |
| `runtime/20-coredns-upstream.env` | Git 管理外 | 実行環境で選定した Pod 到達可能な CoreDNS upstream |

固定 values では、dual-stack Kubernetes IPAM、VXLAN、kube-proxy replacement、基準 MTU `9050`（IPv4 VXLAN の Pod 経路 MTU `9000`）、
multi-device、Fabric 側 NodePort address、BGP Control Plane、Hubble、Egress Gateway を初回から
有効化する。Egress policy と試験アプリだけは初期構築に含めない。

## CLI バイナリ準備と PATH 設定

`helm template` を実行する前に、version を固定した Helm、kubectl、Cilium CLI、Hubble CLI を
Git 管理外の runtime directory へ準備する。system-wide にはインストールせず、この作業 shell の
`PATH` の先頭へ追加する。

```bash
../scripts/k8s-client/prepare-tools.sh \
  --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh \
  --profile k8s_kind/client \
  --check

K8S_CLIENT_RUNTIME="$PWD/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r

command -v helm kubectl cilium hubble
helm version --short
kubectl version --client
cilium version --client
hubble version
```

この手順では `KUBECONFIG` を変更しない。次節で Containerlab が生成した k02 用 kubeconfig を指定する。
新しい shell で作業を再開した場合は、バイナリの再取得は不要だが、`PATH` の設定を再実行する。

## Helm chart cache の準備

固定 version の Cilium／Tetragon chart を公式配布元から Git 管理外の runtime directory へ取得し、
chart 名と version を検証する。以降の静的 render と導入では、この local chart を共通して使用する。

```bash
../scripts/cilium-lab/prepare-helm-charts.sh \
  --profile k8s_kind/client
../scripts/cilium-lab/prepare-helm-charts.sh \
  --profile k8s_kind/client \
  --check

helm show chart k8s_kind/client/runtime/charts/cilium-1.20.1.tgz
helm show chart k8s_kind/client/runtime/charts/tetragon-1.7.0.tgz
```

## kubeconfig の準備

Containerlab が生成する k02 の kubeconfig は、lab 出力 directory 配下に保存される。次のコマンドは
`nxos_fabric/nxos_singlesite` を作業 directory として実行する。

```bash
export CLABNAME="nxos-fabric-singlesite"
export KUBECONFIG="$PWD/clab-${CLABNAME}/adc-k02/k8s_kind/k02/kubeconfig-k02"

ls -l "$KUBECONFIG"
test -r "$KUBECONFIG" || sudo chmod g+r "$KUBECONFIG"
kubectl config get-contexts
kubectl --context kind-adc-k02 get nodes
```

kubeconfig は client certificate と private key を含むため Git へ保存せず、world-readable にしない。
全 Node は Cilium 導入まで `NotReady` でよい。ここでは 3 Node が API から取得できることを確認する。

<a id="staged-install"></a>

## パターン A：段階導入と個別試験

各節を順に実施し、Cilium → checksum → Egress 初期化 → CoreDNS → LB／BGP → Tetragon を揃える。
固定 values は各コンポーネントの初回導入時から最終設計値を使用する。
基盤の初期受入後に、必要な試験 workload／Policy を段階的に追加する。

<a id="cilium-bootstrap"></a>

### Preflight と Node label

初期構築前に host、Kind Node、Fabric link を確認し、worker だけへ BGP speaker label を付与する。

```bash
../scripts/cilium-lab/preflight-host-and-kind.sh --host-only
../scripts/cilium-lab/configure-cilium-node-labels.sh \
  --context kind-adc-k02 --apply
../scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster adc-k02 \
  --kube-context kind-adc-k02
```

preflight 合格後、Cilium を導入する直前の resource baseline を記録する。

```bash
date -Is
awk '/^MemAvailable:/ {print "MemAvailable_MiB=" int($2 / 1024)}' /proc/meminfo
docker stats --no-stream \
  adc-k02-control-plane \
  adc-k02-worker \
  adc-k02-worker2
kubectl --context kind-adc-k02 get pods -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
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
helm template cilium \
  k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/cilium/values/00-base.yaml \
  --values k8s_kind/k02/cilium/values/10-observability.yaml \
  --values k8s_kind/k02/cilium/values/20-singlesite-egress.yaml \
  --values k8s_kind/k02/cilium/runtime/10-k8s-api.yaml \
  > /tmp/cilium-k02-rendered.yaml

test -s /tmp/cilium-k02-rendered.yaml
```

### Cilium の導入

実行前に render 差分と現在の Helm release を確認し、ユーザーがクラスタへの適用を明示した後に実行する。

```bash
helm upgrade --install cilium \
  k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/cilium/values/00-base.yaml \
  --values k8s_kind/k02/cilium/values/10-observability.yaml \
  --values k8s_kind/k02/cilium/values/20-singlesite-egress.yaml \
  --values k8s_kind/k02/cilium/runtime/10-k8s-api.yaml \
  --wait \
  --timeout 10m

helm status cilium \
  --namespace kube-system \
  --kube-context kind-adc-k02
cilium status --context kind-adc-k02 --wait
```

Single-site の初期構築では、`cilium status` の `ClusterMesh: disabled` は想定どおりである。
ClusterMesh は k02 と k03 を使用する multi-site 構築で有効化する。

<a id="checksum-setup"></a>

### checksum 回避策の登録・適用・監視

現行 kernel `5.14.0-611.27.1.el9_7.x86_64` の検証済み構成では、`TI-001` の回避策を維持する。
Cilium と両 worker が Ready となり、`cilium_vxlan` が存在してから実施する。
kernel 更新は multisite 試験後に検討する。別 kernel／image／暗号化設定には無条件で流用しない。

**初回登録だけ：** 対象環境が検証済みの適用条件に一致することと、変更前の offload 値を確認する。
`COMPAT_RESTORE_TX` は記録した元の値、`COMPAT_REASON` は今回の条件確認と対応する証跡 ID に置き換える。
以下の `on` は両 worker の変更前が `on` だった場合の例である。
すでに登録済みなら `enroll` を繰り返さず、後段の再適用へ進む。

```bash
for node in adc-k02-worker adc-k02-worker2; do
  docker exec "$node" uname -r
  docker exec "$node" ethtool -k cilium_vxlan
done

export COMPAT_RESTORE_TX="on"
export COMPAT_REASON="今回確認した適用条件と証跡 ID に置き換える"
python3 "${COMPAT_SCRIPT}" enroll --state "${COMPAT_STATE}" \
  --cluster adc-k02 --context "${KUBE_CONTEXT}" --kubeconfig "${KUBECONFIG}" \
  --node adc-k02-worker --node adc-k02-worker2 \
  --restore-tx "${COMPAT_RESTORE_TX}" --reason "${COMPAT_REASON}"
```

登録時に cluster UID、kernel、image、Cilium の通信設定を固定する。条件が変わった場合は後続処理が停止する。
古い state を上書きして通過させず、変更内容を評価して別パスへ登録する。元の offload 値が不明なら推測しない。

**初回・既存環境共通の再適用と確認：**

```bash
python3 "${COMPAT_SCRIPT}" reconcile --state "${COMPAT_STATE}"
python3 "${COMPAT_SCRIPT}" check --state "${COMPAT_STATE}"
```

**初回の監視登録：** ログアウト後も監視を継続するため user manager の linger を有効にし、
登録した環境専用の 30 秒周期 timer を作成する。既存 unit と内容が異なる場合、installer は上書きせず停止する。

```bash
loginctl enable-linger "$(id -un)"
python3 "${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/install-checksum-monitor.py" \
  --state "${COMPAT_STATE}" --runtime-bin "${K8S_CLIENT_RUNTIME}/bin" \
  --unit cilium-checksum-adc-k02

systemctl --user status cilium-checksum-adc-k02.timer --no-pager
systemctl --user show cilium-checksum-adc-k02.service \
  -p Result -p ExecMainStatus -p ExecMainStartTimestamp
```

既存環境は同じ timer を保持し、上記 status と `check` で確認する。timer active に加え、直近の
`Result=success`／`ExecMainStatus=0` を確認する。登録・再適用は通信試験の代わりにはならない。
適用条件の調査、停止・元の値への復元は [checksum 運用手順](../../../../docs/cilium-lab/runbooks/checksum-compat-operations.md) を参照する。

### Egress interface の初期化

Egress interface には [専用 manifest と helper](manifests/egress-interface-init/README.md) を使用する。
`converge-cilium-lab.sh --profile singlesite-final --apply` は Cilium の準備後に自動適用する。
各手順を個別実行する場合は、Egress Policy より先に同 helper の `--action apply` を実行する。

```bash
../scripts/cilium-lab/configure-egress-interface-init.sh \
  --context "${KUBE_CONTEXT}" --action apply
../scripts/cilium-lab/configure-egress-interface-init.sh \
  --context "${KUBE_CONTEXT}" --action check
kubectl --context "${KUBE_CONTEXT}" -n kube-system get \
  daemonset/k02-egress-interface-init configmap/k02-egress-interface-config
```

対象 worker 2 台の初期化 Pod が Ready、control-plane には配置されないことを確認する。
ConfigMap の `nodes.json` 変更時は helper が rollout を行う。同一設定の再 apply は Pod を再作成しない。
手動のアドレスずれを修復する場合は、同 helper の `--action restart` を明示する。
通常稼働中の定期修復は行わない。Egress IP は保持するだけでは広報されず、専用の試験用 advertisement は別途適用する。

### CoreDNS upstream の設定

Kind Node の `/etc/resolv.conf` は Docker 組み込み DNS を指す場合がある。CoreDNS Pod からその DNS へ到達できない
環境でも再利用できるよう、resolver IP は固定 manifest に保存せず、実行時パラメータとして設定する。

値の優先順位は `--upstream`、環境変数 `COREDNS_UPSTREAM_DNS`、Containerlab host の
`/etc/resolv.conf` から検出した最初の非 loopback IPv4 nameserver の順である。check-only で選定結果を確認してから
`--apply` を指定する。

```bash
../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env

../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env \
  --apply
```

host の nameserver が loopback、link-local、または Pod から到達できない場合は、環境固有値を明示する。

```bash
export COREDNS_UPSTREAM_DNS="${SITE_DNS_RESOLVER_IPV4:?set a Pod-reachable DNS resolver IPv4}"

../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env \
  --apply
```

スクリプトは direct upstream test、CoreDNS ConfigMap patch／rollout、Cluster DNS test を順に実施する。
適用後の test が失敗した場合は元の Corefile へ rollback する。選定値の runtime record は Git へ追加しない。

### LB IPAM／BGP resource の導入

Cilium が Ready になった後、worker 2 Node に集約 prefix の blackhole route を設定してから、
LB IPAM と BGP Control Plane resource を適用する。この段階では試験アプリを適用しない。

```bash
../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh \
  --cluster adc-k02 --action apply
kubectl --context kind-adc-k02 apply \
  -f k8s_kind/k02/cilium/resources/10-lb-ipam.yaml \
  -f k8s_kind/k02/cilium/resources/20-bgp.yaml \
  -f k8s_kind/k02/cilium/resources/21-bgp-planned-shut.yaml

kubectl --context kind-adc-k02 get \
  ciliumloadbalancerippools,ciliumbgpclusterconfigs
cilium bgp peers --context kind-adc-k02
```

worker 2 Node から ADC BGR 2 台へ IPv4／IPv6 で接続するため、合計 8 session が `Established` になることを
確認する。対象の LoadBalancer Service は後続試験で作成するため、この時点では広告経路がなくてもよい。

### Tetragon の導入

repository alias に依存せず、準備済みの local chart から observe-only profile を導入する。

```bash
helm upgrade --install tetragon \
  k8s_kind/client/runtime/charts/tetragon-1.7.0.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/tetragon/values/00-observe-only.yaml \
  --wait \
  --timeout 10m

helm status tetragon \
  --namespace kube-system \
  --kube-context kind-adc-k02
kubectl --context kind-adc-k02 -n kube-system rollout status daemonset/tetragon
kubectl --context kind-adc-k02 -n kube-system rollout status deployment/tetragon-operator
```

<a id="initial-acceptance"></a>

### 初期構築後の受入確認

Cilium、Hubble、Tetragon の状態と、Cilium 導入後の bpffs、Node label、Fabric interface を確認する。

```bash
cilium status --context kind-adc-k02 --wait
kubectl --context kind-adc-k02 get nodes
kubectl --context kind-adc-k02 -n kube-system get pods -o wide

../scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster adc-k02 \
  --kube-context kind-adc-k02
```

preflight は `FAIL=0` を必須とする。`PASS` と `WARN` の件数は、host、Node 数、検査項目によって
変動するため、固定の合格値としない。

`WARN` がある場合は内容を個別に確認する。swap 使用に関する `WARN` は、使用量、導入前からの増減、
性能および Cilium／Tetragon への影響をリソース判定で別途評価する。Cilium 導入後の bpffs 未 mount、
BGP speaker label 未確認など、初期構築完了時に解消すべき `WARN` が残っている場合は合格としない。

10 分 idle 後に resource、Pod restart、OOMKill の有無を記録する。

```bash
date -Is
free -h
awk '/^MemAvailable:/ {print "MemAvailable_MiB=" int($2 / 1024)}' /proc/meminfo
docker stats --no-stream \
  adc-k02-control-plane \
  adc-k02-worker \
  adc-k02-worker2
kubectl --context kind-adc-k02 get pods -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
journalctl -k --since '-15 min' --no-pager | \
  grep -Ei 'oom|out of memory|killed process' || true
```

Hubble certificate 生成 Pod は常駐 Pod ではない。該当 Pod が存在する場合は `Succeeded`、restart `0` を確認する。

```bash
kubectl --context kind-adc-k02 -n kube-system get pods \
  -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount' | \
  awk 'NR == 1 || $1 ~ /^hubble-generate-certs-/'
```

対象 Kind Node container の CPU 合計を 60 回取得し、nearest-rank 法で p95 を計算する。

```bash
for sample in $(seq 1 60); do
  docker stats --no-stream --format '{{.CPUPerc}}' \
    adc-k02-control-plane \
    adc-k02-worker \
    adc-k02-worker2 | \
    tr -d '%' | \
    awk -v timestamp="$(date -Is)" \
      '{total += $1} END {print timestamp, total}'
  sleep 5
done | tee /tmp/k02-idle-cpu.txt

LC_ALL=C sort -n -k2,2 /tmp/k02-idle-cpu.txt | \
  awk '{
    value[NR]=$2
  }
  END {
    p95_pos=int((NR * 95 + 99) / 100)
    printf "samples=%d CPU_p95_percent=%.2f\n", NR, value[p95_pos]
  }'
```

初期構築後の `MemAvailable` は `4096 MiB` 以上、OOMKill は 0 件、idle 後の restart 増加は 0 件を
最低合格値とする。Cilium／Hubble／Tetragon の増分 memory は `4096 MiB` 以下を暫定上限とし、
導入直前と 10 分 idle 後の同形式の記録を比較する。CPU p95 は `200%` 以下を初期合格値、`100%` 以下を
推奨運用値とする。詳細は
[リソース設計と preflight](../../../../docs/cilium-lab/runbooks/resource-and-preflight.md)を参照する。

LoadBalancer VIP の割り当て、`/26`／`/112` の広告、Hubble flow、Tetragon event は、初期 platform の
resource 判定後に [Stage 2A lab-smoke 実行手順](manifests/validation/lab-smoke/README.md)から開始し、
`manifests/validation/` の試験 workload と policy を段階適用して確認する。

`lab-smoke` の初期合格後は、
[Network Policy／Tetragon 検証計画](../../../../docs/cilium-lab/tests/network-policy-and-tetragon-test-plan.md)の
`NP-00` から後続試験を開始する。

既存の `manifest/` は旧 MetalLB／demo 検証用であり、Cilium 初期構築時に一括適用しない。

<a id="direct-final-install"></a>

## パターン B：個別試験を行わず最終構成を最初から導入

Containerlab／kind の Node と Fabric が作成済みで、Cilium をこれから導入する環境が対象である。
Node／Fabric の前提確認を済ませたうえで、この節から作業環境・CLI・chart を準備できる。
試験用リソースの撤去や既存 Helm release の退避は不要。
既に試験設定が入っている環境には [試験後の撤去・復元](#final-convergence) を使用する。

### 1. 初回用の入力と出力先を準備する

Containerlab 実行ホストの Bash で、リポジトリ内の任意のディレクトリから開始する。
新しいシェルでは、まず次の環境変数を設定する。Git 管理していない配置では `REPO_ROOT` を実際の絶対パスへ置き換える。
最後の入力欄には、この環境で使用する DNS resolver の IPv4 を入力する。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export SITE_TYPE="singlesite"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_${SITE_TYPE}"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
export KUBECONFIG="${LAB_ROOT}/clab-nxos-fabric-singlesite/adc-k02/k8s_kind/k02/kubeconfig-k02"
export KUBE_CONTEXT="kind-adc-k02"
export COMPAT_SCRIPT="${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/checksum-compat.py"
export COMPAT_STATE="${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02/checksum-compat.json"
cd "${LAB_ROOT}"

read -r -p 'Pod から使用する DNS resolver IPv4: ' SITE_DNS_RESOLVER_IPV4
export SITE_DNS_RESOLVER_IPV4
```

`KUBECONFIG` は構築時に生成された管理 API 用ファイルを使用する。
`COMPAT_STATE` は後続の初回登録先であり、新規クラスタへ古い cluster UID の state を流用しない。
既存 timer がある環境では、その登録先と一致することを確認する。

`SITE_DNS_RESOLVER_IPV4` に、この環境の Pod から利用する DNS resolver の IPv4 を設定する。
初回は `runtime/20-coredns-upstream.env` がないため、過去の保存値を読み込まない。
DNS 到達性は導入時に helper が確認する。確認に失敗した場合は後続へ進まない。

CLI・chart の準備コマンドは未準備なら取得し、続く `--check` で保存済みファイルを検査する。
この節は Node／Fabric の作成や修正を行わない。各コマンドで失敗した場合は後続へ進まず、原因を解消する。

```bash
export COREDNS_UPSTREAM_DNS="${SITE_DNS_RESOLVER_IPV4:?Pod から使用する DNS resolver IPv4 を設定してください}"
umask 077
mkdir -p "${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02"
export FINAL_DIR="$(mktemp -d "${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02/install-final-XXXXXXXX")"
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client --check
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile singlesite-final --context-k02 "${KUBE_CONTEXT}" \
  --output-dir "${FINAL_DIR}/rendered"
```

この段階は offline render のみ。仮の API address と試験用 manifest も出力されるため、
出力 directory 全体を `kubectl apply -f` せず、冒頭の最終構成と照合する。

### 2. Cilium と checksum 回避策を初回準備する

現行 kernel の回避策は、Cilium が作成する `cilium_vxlan` と cluster UID を確認して登録するため、
Cilium 未導入の状態では state を作成できない。次の 2 範囲だけを先に実施する。
これは依存関係を満たす初期化であり、個別試験の実施を前提としない。

1. [Preflight と Node label](#cilium-bootstrap) から「Cilium の導入」までを実施する。API values を生成し、最終 values の Cilium を導入する。
2. [checksum 回避策の登録・適用・監視](#checksum-setup) を実施する。条件確認、元の offload 値の記録、初回登録、再適用、timer の登録と成功確認まで完了する。

以前のクラスタの state は流用しない。異なる kernel／image では適用条件を再評価する。
一括 driver は初回登録と timer 作成を行わないため、現行構成の新規導入を 1 コマンドだけで完了する手順ではない。

### 3. 常設設定をまとめて適用する

```bash
python3 "${COMPAT_SCRIPT}" check --state "${COMPAT_STATE}"
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile singlesite-final --context-k02 "${KUBE_CONTEXT}" \
  --coredns-upstream "${COREDNS_UPSTREAM_DNS:?初回用 DNS の設定が必要です}" \
  --checksum-state-k02 "${COMPAT_STATE}" \
  --output-dir "${FINAL_DIR}/applied-render" \
  --apply
```

driver は Node label／preflight／API values → Cilium → checksum 再適用・確認 → CoreDNS →
集約 blackhole／LB IPAM／BGP → Egress 初期化 → Tetragon → readiness を実行する。
Hubble は Cilium values に含む。Egress の DaemonSet・ConfigMap・対象 label・`egress0`／IP まで揃える。
試験用 Egress Policy／広報、lab-smoke、Network Policy／Tetragon の試験アプリは適用しない。
途中失敗時の全設定の自動 rollback は行わない。失敗箇所を確認して対処する。

### 4. 最終状態を確認する

[共通の最終状態確認](#final-state-check) を実施する。`FINAL_DIR` は上で作成した保存先をそのまま使用する。
ここまでで常設基盤の導入が完了する。個別試験を省略した項目は未検証として扱う。
必要な段階で [初期受入・個別試験](#initial-acceptance) を追加実施できる。

<a id="final-convergence"></a>

## 補足：試験後の撤去・最終構成への復元

既存 k02 を、冒頭の常設基盤へ戻す手順である。新しいシェルでは「共通の作業環境」を再設定する。
一括 driver は必要な resource を適用するが、試験用 Policy の削除や保守用 label の解除は自動実行しない。
また、設定と状態の確認は全体 connectivity／性能試験の合格とは分けて記録する。

### 1. 試験を終了し、現在値を保存する

試験・capture・外部専用サーバを、それぞれの試験セッションで記録した終了手順／PID に従って停止する。
UI／CLI の継続観測と port-forward は起動した端末で `Ctrl+C` を押す。証跡と既存のハッシュは保持する。
次の保存先は今回の最終設定作業専用であり、過去セッションへ追記しない。

```bash
umask 077
mkdir -p "${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02"
export FINAL_DIR="$(mktemp -d "${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02/finalize-XXXXXXXX")"
helm get values cilium --kube-context "${KUBE_CONTEXT}" -n kube-system -o yaml \
  > "${FINAL_DIR}/cilium-values-before.yaml"
helm get values tetragon --kube-context "${KUBE_CONTEXT}" -n kube-system -o yaml \
  > "${FINAL_DIR}/tetragon-values-before.yaml"
kubectl --context "${KUBE_CONTEXT}" get nodes -o yaml > "${FINAL_DIR}/nodes-before.yaml"
kubectl --context "${KUBE_CONTEXT}" -n kube-system get configmap coredns -o yaml \
  > "${FINAL_DIR}/coredns-before.yaml"
kubectl --context "${KUBE_CONTEXT}" get ciliumegressgatewaypolicies,ciliumbgpadvertisements -o yaml \
  > "${FINAL_DIR}/egress-bgp-before.yaml"
```

### 2. 試験用リソースと一時状態を戻す

以下は本書の試験専用 namespace／Policy に対する撤去である。対象が今回の試験用であり、
別用途のアプリを追加していないことを確認してから実行する。Egress Policy を先に削除して通常通信へ戻し、
専用広報を削除する。通常の試験終了時は `egress0` と初期化 DaemonSet を削除しない。

```bash
kubectl --context "${KUBE_CONTEXT}" get namespace \
  egress-probe cilium-lab-policy cilium-lab-tetragon-control --ignore-not-found
kubectl --context "${KUBE_CONTEXT}" delete -k \
  k8s_kind/k02/cilium/manifests/validation/egress/gw-a --ignore-not-found
```

`gw-a` と `gw-b` は同名の IPv4／IPv6 Policy を更新するため、上記で両 profile の対象 Policy を撤去できる。
通常送信元への復帰を確認してから、次へ進む。

```bash
kubectl --context "${KUBE_CONTEXT}" delete -k \
  k8s_kind/k02/cilium/manifests/validation/egress/bgp --ignore-not-found
cilium bgp routes advertised ipv4 unicast --context "${KUBE_CONTEXT}"
cilium bgp routes advertised ipv6 unicast --context "${KUBE_CONTEXT}"
kubectl --context "${KUBE_CONTEXT}" delete namespace \
  egress-probe cilium-lab-policy cilium-lab-tetragon-control \
  --ignore-not-found --timeout=120s
```

BGR／Leaf 側でも Egress の個別・集約経路が撤回され、既存 LB 経路が維持されることを確認する。
`cilium-lab-policy` の削除には試験用 NetworkPolicy／CiliumNetworkPolicy／TracingPolicyNamespaced の撤去が含まれる。
CLI connectivity の試験用 namespace は実行時に指定した名前を確認して別途撤去する。名前の一括 wildcard 削除は行わない。
`cilium-lab-smoke` は継続的な LB 確認用に保持してよい。基盤だけに戻す場合は次も実行する。

```bash
kubectl --context "${KUBE_CONTEXT}" delete -k \
  k8s_kind/k02/cilium/manifests/validation/lab-smoke --ignore-not-found
```

BGP 保守試験を実施した場合は、復帰させる Node の Ready と経路を確認してから、対象 Node ごとに
`bgp-maintenance` label を削除する。normal selector は label が存在しない状態であり、`normal` という値の設定ではない。
cordon／drain した Node の uncordon も、今回停止した Node だけに実施する。

```bash
# 例：今回の保守対象が adc-k02-worker だった場合だけ実行する。
kubectl --context "${KUBE_CONTEXT}" label node adc-k02-worker bgp-maintenance-
kubectl --context "${KUBE_CONTEXT}" uncordon adc-k02-worker
```

TG-07 の一時停止 selector が残っている場合は、今回追加したキーだけを除去する。

```bash
kubectl --context "${KUBE_CONTEXT}" -n kube-system get daemonset tetragon \
  -o jsonpath='{.spec.template.spec.nodeSelector}{"\n"}'
# cilium-lab/tg07-paused が今回の試験で残っている場合だけ実行する。
kubectl --context "${KUBE_CONTEXT}" -n kube-system patch daemonset tetragon --type=merge \
  -p '{"spec":{"template":{"spec":{"nodeSelector":{"cilium-lab/tg07-paused":null}}}}}'
```

### 3. 最終設定の入力を確認して offline render する

CoreDNS は導入時に保存した upstream を明示して再利用する。record がない場合は、本書の
CoreDNS 手順で resolver を選定する。checksum は既存の登録 state が同じ環境に一致することを確認する。
試験で Helm values 自体を編集した場合は、冒頭の基準値へ戻した差分を確認してから render する。

```bash
export COREDNS_UPSTREAM_DNS="$(awk -F= '$1 == "COREDNS_UPSTREAM_DNS" {print $2}' \
  k8s_kind/k02/cilium/runtime/20-coredns-upstream.env)"
: "${COREDNS_UPSTREAM_DNS:?CoreDNS の選定済み IPv4 が必要です}"
test -f "${COMPAT_STATE}"
python3 "${COMPAT_SCRIPT}" reconcile --state "${COMPAT_STATE}"
python3 "${COMPAT_SCRIPT}" check --state "${COMPAT_STATE}"

../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check
../scripts/cilium-lab/prepare-helm-charts.sh --profile k8s_kind/client --check
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile singlesite-final --context-k02 "${KUBE_CONTEXT}" \
  --output-dir "${FINAL_DIR}/rendered"
```

最後のコマンドは `--apply` がないため offline render のみ。
出力には仮の API address `192.0.2.10` と試験用 manifest の render も含まれるため、出力 directory 全体を
`kubectl apply -f` しない。実適用では driver が API address を取得し、対象の常設リソースだけを依存順で適用する。

### 4. 常設設定を一括再適用する

render と現在値の差分を確認し、対象クラスタへの設定反映を行う段階で実行する。
現在の kernel 構成では checksum state と CoreDNS upstream を両方渡す。

```bash
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile singlesite-final --context-k02 "${KUBE_CONTEXT}" \
  --coredns-upstream "${COREDNS_UPSTREAM_DNS}" \
  --checksum-state-k02 "${COMPAT_STATE}" \
  --output-dir "${FINAL_DIR}/applied-render" \
  --apply
```

適用順は Node speaker label／preflight／API values 生成 → Cilium → checksum 再適用・確認 →
CoreDNS → 集約 blackhole／LB IPAM／BGP → Egress 初期化 → Tetragon → readiness 確認。
このオプションでは checksum の初回登録や timer の作成は行わないため、本書の checksum 節で先に準備する。
途中失敗時は後続へ進まない。自動で全設定を rollback する処理ではなく、保存した変更前値と失敗箇所を確認して対処する。

[共通の最終状態確認](#final-state-check) へ進む。

<a id="final-state-check"></a>

## 共通：最終状態の確認

```bash
kubectl --context "${KUBE_CONTEXT}" get nodes -o wide \
  -L bgp-speaker,bgp-maintenance,lab.cilium.io/egress-gateway
cilium status --context "${KUBE_CONTEXT}"
cilium bgp peers --context "${KUBE_CONTEXT}"
hubble status --kube-context "${KUBE_CONTEXT}" -P
kubectl --context "${KUBE_CONTEXT}" -n kube-system get \
  daemonset/cilium daemonset/tetragon daemonset/k02-egress-interface-init \
  deployment/hubble-relay deployment/hubble-ui deployment/tetragon-operator
../scripts/cilium-lab/configure-egress-interface-init.sh \
  --context "${KUBE_CONTEXT}" --action check
../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh \
  --cluster adc-k02 --action check
../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context "${KUBE_CONTEXT}" --upstream "${COREDNS_UPSTREAM_DNS}"
python3 "${COMPAT_SCRIPT}" check --state "${COMPAT_STATE}"
systemctl --user is-active cilium-checksum-adc-k02.timer
systemctl --user show cilium-checksum-adc-k02.service \
  -p Result -p ExecMainStatus -p ExecMainStartTimestamp
helm get values cilium --kube-context "${KUBE_CONTEXT}" -n kube-system -o yaml \
  > "${FINAL_DIR}/cilium-values-after.yaml"
helm get values tetragon --kube-context "${KUBE_CONTEXT}" -n kube-system -o yaml \
  > "${FINAL_DIR}/tetragon-values-after.yaml"
```

Node 3 台 Ready、Cilium／Tetragon 各 3 台、Egress 初期化 2 台、BGP 8 session Established を確認する。
checksum は timer active と直近 service 成功を両方確認する。再び Node／Fabric の前提確認を行い、
workload がある場合は、Pod 経路 MTU `9000` と IPv4／IPv6 の実通信も確認する。
パターン B で試験 workload を配置しない場合、実通信・MTU の試験結果は未検証として記録する。
試験用 Egress 広報のない最終状態では、保持した Egress IP の経路が外部へ広告されないことが期待値となる。

日常の環境変数・UI アクセスは [single-site の操作環境](../../../README.md#k02-client-environment)、
試験ごとの通信確認は [lab-smoke](manifests/validation/lab-smoke/README.md) と
[試験手順一覧](../../../../docs/cilium-lab/tests/README.md) を参照する。

**検証範囲：** 本書の Bash 構文、参照リンク、`singlesite-final` の offline render は 2026-09-13 に確認した。
個別設定と Egress helper の適用・再適用、既存環境での通信試験は保存済み結果を継承する。
全体 driver の `--apply` をこの手順で一括再実行した結果、新規 Node からの再現性、Node 再起動後の復旧は未検証。
初回適用の再現性は multisite 構築時に確認する。現在の残課題は [status](../../../../docs/cilium-lab/status.md) を参照する。
