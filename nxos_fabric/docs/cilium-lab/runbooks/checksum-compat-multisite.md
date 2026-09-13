# multisite の checksum 回避策：初回登録・監視・一括再適用

2026-09-13 時点で手順と一括 driver の対応を準備した。multisite の構築・適用・通信受入は未実施。
この手順は kernel を更新せず、必要なクラスタだけに暫定回避策を明示登録する。
通常の `multisite-final` は Egress Gateway を無効とし、Egress 初期化も行わない。

## 1. 適用条件と処理の順序

single-site では実行ホスト kernel `5.14.0-611.27.1.el9_7.x86_64`、Cilium `v1.20.1`、
VXLAN／dual-stack／LB SNAT で Node 間 IPv6 LB の TCP checksum 不正が再現した。
両 worker の `cilium_vxlan` の `tx-checksum-ip-generic` を `off` にする回避策を検証済みである。
kind は実行ホストの kernel を共有する。同じ版番号だけで multisite の通信合格とはしない。
[問題の意味と影響](checksum-compat-operations.md)、[kernel の判定手順](kernel-compatibility-policy.md) を先に確認する。

| 段階 | 処理 | 自動化の範囲 |
|---|---|---|
| 導入前 | host kernel／helper 対応を確認し、必要なクラスタを決める | 版番号による自動判定・自動適用はしない |
| 初回だけ | 最終 values で Cilium を導入し、対象 worker の元の offload 値を記録する | 下記の bootstrap 手順 |
| 初回だけ | 新しい cluster UID・image・通信設定に対して state を登録し、適用・監視を開始する | `checksum-compat.py` と monitor installer |
| 常設設定の適用 | 両 state の所属を確認し、Cilium → checksum → CoreDNS → LB／BGP を各クラスタで実施する | 拡張した `converge-cilium-lab.sh` |
| 適用後 | 設定維持と IPv4／IPv6 の実通信を確認する | 状態確認だけで通信受入を代替しない |

`--checksum-state-k02`／`--checksum-state-k03` は登録済み state の再適用用である。
初回登録と timer 作成は別手順であり、Cilium が未導入の新規環境でいきなり両オプションを指定しない。
helper が判定不能、または未知の kernel／image の場合は、必要性と回避策の適用範囲を評価してから進む。
kernel 更新は multisite 試験後に検討する方針を維持する。

## 2. 旧 single-site の監視と実行環境を分ける

今回の multisite 実行先は **clab02**。single-site が動く clab01 とは別ホストなので、
**clab01 の既存 timer は維持し、下記の停止操作は実施しない。**
clab02 の kernel は `5.14.0-611.49.1.el9_7.x86_64`（2026-09-13 確認）で、
single-site の検証済み版とは異なる。clab02 で helper と対象経路を評価し、回避策の要否を判断する。
同じ context 名でも別クラスタのため、clab01 の kubeconfig／state を流用しない。

以下は将来、**同じ実行ホスト上で** single-site を multisite に置き換える場合だけの手順である。
同名 `adc-k02-*` Node を破棄・再作成する前に、そのホストの旧 timer と実行中 service を停止する。

```bash
systemctl --user show cilium-checksum-adc-k02.service -p ExecStart -p Result -p ExecMainStatus
systemctl --user disable --now cilium-checksum-adc-k02.timer
systemctl --user stop cilium-checksum-adc-k02.service
systemctl --user is-active cilium-checksum-adc-k02.timer cilium-checksum-adc-k02.service
```

最後の `is-active` は両方 `inactive`、非 0 終了が期待値。Node の停止・破棄・作成はこの手順には含めない。
旧 state・unit・証跡は保持する。新しい Node に旧 state の `restore` を実行しない。
旧 timer は cluster UID 不一致でも変更を拒否するが、同一ホストで置換済みの旧クラスタへの監視は停止する。

multisite の Node／Fabric を構築後、実行ホストのリポジトリ内で次を設定する。
CLI／chart は [k02 README](../../../nxos_multisite/k8s_kind/k02/cilium/README.md#multisite-preparation) の準備を完了する。
使用する共通スクリプトは実行ホストへ同じ版を配置する。Git 同期は前提にしない。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_multisite"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
export KUBECONFIG_K02="${LAB_ROOT}/clab-nxos-fabric-multisite/adc-k02/k8s_kind/k02/kubeconfig-k02"
export KUBECONFIG_K03="${LAB_ROOT}/clab-nxos-fabric-multisite/bdc-k03/k8s_kind/k03/kubeconfig-k03"
export KUBECONFIG="${KUBECONFIG_K02}:${KUBECONFIG_K03}"
export KUBE_CONTEXT_K02="kind-adc-k02"
export KUBE_CONTEXT_K03="kind-bdc-k03"
export COMPAT_SCRIPT="${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/checksum-compat.py"
cd "${LAB_ROOT}"

export K02_UID="$(kubectl --kubeconfig "$KUBECONFIG_K02" --context "$KUBE_CONTEXT_K02" get namespace kube-system -o jsonpath='{.metadata.uid}')"
export K03_UID="$(kubectl --kubeconfig "$KUBECONFIG_K03" --context "$KUBE_CONTEXT_K03" get namespace kube-system -o jsonpath='{.metadata.uid}')"
: "${K02_UID:?k02 API の UID 取得が必要です}" "${K03_UID:?k03 API の UID 取得が必要です}"
export COMPAT_STATE_K02="${LAB_ROOT}/operations/cilium-lab/runtime/adc-k02/${K02_UID}/checksum-compat.json"
export COMPAT_STATE_K03="${LAB_ROOT}/operations/cilium-lab/runtime/bdc-k03/${K03_UID}/checksum-compat.json"
export COMPAT_UNIT_K02="cilium-checksum-multisite-adc-k02-${K02_UID}"
export COMPAT_UNIT_K03="cilium-checksum-multisite-bdc-k03-${K03_UID}"
umask 077
mkdir -p "${LAB_ROOT}/operations/cilium-lab/runtime"
export COMPAT_EVIDENCE="$(mktemp -d "${LAB_ROOT}/operations/cilium-lab/runtime/checksum-setup-XXXXXXXX")"
uname -r > "${COMPAT_EVIDENCE}/host-kernel.txt"
```

各 state の `--kubeconfig` には単一ファイルを指定する。`KUBECONFIG` の `:` 区切り文字列は渡さない。
state と unit 名に新しい cluster UID を含め、single-site と過去の multisite 登録を分離する。
シェルを開き直した場合も現在の UID を取得して同じパスを参照する。過去の state をコピーして埋めない。

## 3. 初回だけ：Cilium を bootstrap する

Cilium が未導入のクラスタに実施する。既に導入済みなら、同じ最終 values・Fabric Node IP・MTU を
確認して次節へ進む。下記は Cilium と共有 CA までを揃え、CoreDNS／LB／BGP は後で適用する。
両 API で各 3 Node が見えること、Node Fabric MTU `9150`、Leaf L2／Fabric `9216` と LACP を先に確認する。

```bash
bash <<'BASH'
set -euo pipefail
for site in k02 k03; do
  if [[ "$site" == k02 ]]; then
    cluster=adc-k02; context="$KUBE_CONTEXT_K02"
  else
    cluster=bdc-k03; context="$KUBE_CONTEXT_K03"
  fi
  ../scripts/cilium-lab/configure-cilium-node-labels.sh --context "$context" --apply
  ../scripts/cilium-lab/preflight-host-and-kind.sh --cluster "$cluster" --kube-context "$context"
  ../scripts/cilium-lab/render-k8s-api-values.sh \
    --cluster "$cluster" --output "k8s_kind/${site}/cilium/runtime/10-k8s-api.yaml"
  if [[ "$site" == k03 ]]; then
    ../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
      --source-context "$KUBE_CONTEXT_K02" --target-context "$KUBE_CONTEXT_K03" --apply
  fi
  helm upgrade --install cilium k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
    --namespace kube-system --kube-context "$context" \
    --values "k8s_kind/${site}/cilium/values/00-base.yaml" \
    --values "k8s_kind/${site}/cilium/values/10-observability.yaml" \
    --values "k8s_kind/${site}/cilium/values/20-multisite-clustermesh.yaml" \
    --values "k8s_kind/${site}/cilium/runtime/10-k8s-api.yaml" \
    --wait --timeout 10m
  cilium status --context "$context" --wait
done
BASH
```

既存 CA が異なる場合、helper は停止する。通常手順で `--replace-existing` を使用しない。
この時点では Mesh VIP の到達や両クラスタの Mesh 接続完了は要求しない。
Cilium／対象 worker が Ready にならない場合は後続の登録へ進まない。

## 4. クラスタごとに元の値を記録し、登録・再適用する

以下は両クラスタで回避策を使用する場合の例。元の offload 値を確認してから登録する。
1 state は両 worker を対象とし、元の値が両 worker で同じであることを確認する。
異なる場合は一律に `on` として登録せず、復元方針を整理してから進む。
`enroll` 自体は NIC を変更しない。登録は実通信の合格を意味しない。

**4 節と 5 節を k02 で完了してから、k03 でも繰り返す。**
次の `COMPAT_SITE` は 1 回目に `k02`、2 回目に `k03` を設定する。

```bash
export COMPAT_SITE=k02
case "$COMPAT_SITE" in
  k02)
    export COMPAT_CLUSTER=adc-k02 COMPAT_CONTEXT="$KUBE_CONTEXT_K02"
    export COMPAT_KUBECONFIG="$KUBECONFIG_K02" COMPAT_STATE="$COMPAT_STATE_K02" COMPAT_UNIT="$COMPAT_UNIT_K02"
    ;;
  k03)
    export COMPAT_CLUSTER=bdc-k03 COMPAT_CONTEXT="$KUBE_CONTEXT_K03"
    export COMPAT_KUBECONFIG="$KUBECONFIG_K03" COMPAT_STATE="$COMPAT_STATE_K03" COMPAT_UNIT="$COMPAT_UNIT_K03"
    ;;
  *) printf 'COMPAT_SITE は k02 または k03 を指定してください。\n' >&2; exit 1 ;;
esac
```

選択したクラスタで実施する。

```bash
for node in "${COMPAT_CLUSTER}-worker" "${COMPAT_CLUSTER}-worker2"; do
  docker exec "$node" uname -r
  docker exec "$node" ethtool -k cilium_vxlan | tee "${COMPAT_EVIDENCE}/${node}-offload-before.txt"
done
read -r -p '両 worker で確認した変更前の tx-checksum-ip-generic (on/off): ' COMPAT_RESTORE_TX
read -r -p 'kernel/helper の確認結果と今回の適用根拠・証跡 ID: ' COMPAT_REASON
export COMPAT_RESTORE_TX COMPAT_REASON
python3 "$COMPAT_SCRIPT" enroll --state "$COMPAT_STATE" \
  --cluster "$COMPAT_CLUSTER" --context "$COMPAT_CONTEXT" --kubeconfig "$COMPAT_KUBECONFIG" \
  --node "${COMPAT_CLUSTER}-worker" --node "${COMPAT_CLUSTER}-worker2" \
  --restore-tx "${COMPAT_RESTORE_TX:?元の値を指定してください}" --reason "${COMPAT_REASON:?適用根拠を記録してください}"
python3 "$COMPAT_SCRIPT" reconcile --state "$COMPAT_STATE"
python3 "$COMPAT_SCRIPT" check --state "$COMPAT_STATE"
```

各コマンドが失敗した場合は後続へ進まない。登録済みなら `enroll` は再実行せず、`check`／`reconcile` を使用する。
state は cluster UID、host kernel、Node／Cilium image、登録対象の通信設定に束縛される。
一致しない場合は再評価する。古い state の内容を手編集して照合を通過させない。

## 5. クラスタ専用の timer を作成する

前節で選択・登録したクラスタのまま実施する。k02 と k03 でそれぞれ作成する。

```bash
loginctl enable-linger "$(id -un)"
python3 "${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/install-checksum-monitor.py" \
  --state "$COMPAT_STATE" --runtime-bin "${K8S_CLIENT_RUNTIME}/bin" --unit "$COMPAT_UNIT"
systemctl --user is-active "${COMPAT_UNIT}.timer"
systemctl --user show "${COMPAT_UNIT}.service" -p Result -p ExecMainStatus -p ExecMainStartTimestamp
```

timer は 30 秒周期。`active` と直近の `Result=success`／`ExecMainStatus=0` を確認する。
対象外 Node・別クラスタの state は使用しない。異なる内容の既存 unit は installer が上書きせず拒否する。

## 6. 両クラスタの常設設定を一括適用する

DNS は両クラスタの Pod から使用できる同一 resolver を選定する。別々の DNS が必要な場合は
各 README の個別導入を使用し、各クラスタで Cilium → checksum → CoreDNS の順序を維持する。

```bash
read -r -p '両クラスタで使用する DNS resolver IPv4: ' COREDNS_UPSTREAM_DNS
export COREDNS_UPSTREAM_DNS
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile multisite-final \
  --context-k02 "$KUBE_CONTEXT_K02" --context-k03 "$KUBE_CONTEXT_K03" \
  --checksum-state-k02 "$COMPAT_STATE_K02" --checksum-state-k03 "$COMPAT_STATE_K03" \
  --output-dir "${COMPAT_EVIDENCE}/rendered"
```

まず offline render を確認する。出力全体を `kubectl apply -f` しない。

```bash
../scripts/cilium-lab/converge-cilium-lab.sh \
  --profile multisite-final \
  --context-k02 "$KUBE_CONTEXT_K02" --context-k03 "$KUBE_CONTEXT_K03" \
  --checksum-state-k02 "$COMPAT_STATE_K02" --checksum-state-k03 "$COMPAT_STATE_K03" \
  --coredns-upstream "${COREDNS_UPSTREAM_DNS:?DNS resolver を指定してください}" \
  --output-dir "${COMPAT_EVIDENCE}/applied-render" --apply
```

両 state の cluster／context／worker 対象を確認し、実適用時は最初の設定変更前に
選択 context と state 内 kubeconfig の両方の cluster UID を照合する。k03 が不一致でも k02 の変更を始めない。
その後、各 Cilium 導入直後・CoreDNS 設定前に `reconcile`／`check` を実行する。
kernel／image／通信設定の不一致や再適用失敗時は停止する。ただし途中までの Helm 等を自動 rollback はしない。

回避策が不要と確認したクラスタのオプションだけ省略できる。省略は正常性の自動判定ではなく、
そのクラスタへの回避策適用を行わない指定である。未確認のまま省略しない。

## 7. 最終確認と解除・再構築

```bash
python3 "$COMPAT_SCRIPT" check --state "$COMPAT_STATE_K02"
python3 "$COMPAT_SCRIPT" check --state "$COMPAT_STATE_K03"
for unit in "$COMPAT_UNIT_K02" "$COMPAT_UNIT_K03"; do
  systemctl --user is-active "${unit}.timer"
  systemctl --user show "${unit}.service" -p Result -p ExecMainStatus -p ExecMainStartTimestamp
done
```

各クラスタの API／Node／Cilium／BGP／CoreDNS に加え、IPv6 Service の remote backend 応答、
Mesh API の dual-stack VIP 到達、DCI 越しの通信を [Cluster Mesh 受入設計](../design/clustermesh-fabric-dci-and-acceptance.md) に沿って確認する。
必要に応じて受信側 capture で checksum を確認する。状態確認だけで multisite の回避策を検証済みにはしない。

kernel／Cilium の更新後は [解除条件](kernel-compatibility-policy.md#恒久対応後に回避策を解除する条件) を確認する。
対象クラスタが同じ登録条件のまま解除する場合は、その timer と service を停止してから
[共通運用手順の restore](checksum-compat-operations.md) で元の値へ戻す。
クラスタを作り直す場合は旧 timer を停止し、旧 state を保存したまま新 UID で登録し直す。

## 8. 今回の確認範囲

- checksum 関連の 17 テストが成功。一括 driver の k02／k03 対応、state の取り違え・UID 不一致の拒否、checksum 失敗時の後続停止を隔離した fake tool で確認した。
- single-site の既存 `--checksum-state-k02` の動作と、offline render 時にクラスタへ接続しないことを確認した。
- 両 profile の実 chart による offline render、手順の Bash 構文とリンクを確認した。
- 公開用 config 検査は 122 ファイルで成功し、変更 0、除去対象 username 0。既存の lab 用管理設定 530 行は保持し、global address／private key の検査に合格した。
- multisite 実環境の bootstrap・初回登録・timer・一括適用・通信は未実施。変更した driver と手順はローカルで準備済みで、実行ホストへの新版配送は構築前に行う。
