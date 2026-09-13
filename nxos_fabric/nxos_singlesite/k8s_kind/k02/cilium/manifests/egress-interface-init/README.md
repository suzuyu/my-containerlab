# k02 Egress interface 初期設定

この manifest は、Egress Gateway 候補 Node の `egress0` と Egress IP を初期設定する。
コマンドは `nxos_fabric/nxos_singlesite` から実行する。single-site k02 専用であり、multisite k02／k03 は対象外。
ConfigMap は Node ごとの desired state を表す `nodes.json` だけを保持し、処理は DaemonSet の
`STARTUP_SCRIPT` に記載する。

DaemonSet は `lab.cilium.io/egress-gateway=true` の Node だけに配置する。現在の対象は次の 2 Node である。
label を付ける Node 名は `nodes.json` の key と一致させる。
IP は IPv4 `/32`、IPv6 `/128` の正規化表記を使用する。Node 名と重複アドレスは helper が適用前に検査する。

```bash
kubectl --context kind-adc-k02 label node \
  adc-k02-worker \
  adc-k02-worker2 \
  lab.cilium.io/egress-gateway=true \
  --overwrite
```

使用する `quay.io/cilium/startup-script` は Cilium chart `1.20.1` と同じ digest に固定している。
この image は host namespace で `STARTUP_SCRIPT` を実行するため、対象 Node には `bash`、`ip`、`jq` が必要である。
適用前に次を確認する。

```bash
for node in adc-k02-worker adc-k02-worker2; do
  docker exec "$node" sh -c 'command -v bash && command -v ip && command -v jq'
done
```

通常の構築・再適用は次の helper を使用する。全 Node の IP・所有 marker と対象 Node の host コマンドを
検査し、label と manifest を収束させる。ConfigMap の内容が変わった場合は rollout も実施する。

```bash
bash ../scripts/cilium-lab/configure-egress-interface-init.sh --context kind-adc-k02 --action apply
bash ../scripts/cilium-lab/configure-egress-interface-init.sh --context kind-adc-k02 --action check
```

`converge-cilium-lab.sh --profile singlesite-final --apply` も Cilium の準備後に同じ helper を呼ぶ。
手動で段階を確認する場合は以下を使用する。

```bash
EGRESS_INIT_ROOT="k8s_kind/k02/cilium/manifests/egress-interface-init"

kubectl --context kind-adc-k02 kustomize "${EGRESS_INIT_ROOT}"
kubectl --context kind-adc-k02 apply --dry-run=server -k "${EGRESS_INIT_ROOT}"
kubectl --context kind-adc-k02 diff -k "${EGRESS_INIT_ROOT}" || test "$?" -eq 1
kubectl --context kind-adc-k02 apply -k "${EGRESS_INIT_ROOT}"
kubectl --context kind-adc-k02 -n kube-system rollout status \
  daemonset/k02-egress-interface-init
```

初回 Pod 作成時は `egress0` を作成し、desired address が使用可能になった後に古い global address を削除する。
所有 marker が異なる `egress0`、`dummy` ではない同名 interface、Node 内の別 interface に存在する desired address は
変更せずエラーにする。通常稼働中は checkpoint の有無だけを確認し、interface を定期的に変更しない。

`nodes.json` は環境変数として Pod 起動時に読み込む。ConfigMap の変更後は DaemonSet を再起動する。
Pod UID ごとに host の `/run/cilium-egress-interface-init/` へ checkpoint を作成するため、新しい Pod では
初期化処理が再実行される。

```bash
kubectl --context kind-adc-k02 apply -k "${EGRESS_INIT_ROOT}"
kubectl --context kind-adc-k02 -n kube-system rollout restart \
  daemonset/k02-egress-interface-init
kubectl --context kind-adc-k02 -n kube-system rollout status \
  daemonset/k02-egress-interface-init

kubectl --context kind-adc-k02 -n kube-system logs \
  daemonset/k02-egress-interface-init --all-pods=true
```

Cilium は Node の address 変更へ自動追従しないため、Egress IP を変更した後は対応する
`CiliumEgressGatewayPolicy` を再適用する。稼働中の Egress IP を変更するときは、新 address の追加と
BGP 経路確認、Policy 切替、旧 address の削除を段階的に行う。まず旧 address と新 address の両方を
`nodes.json` の配列へ残して rollout し、Policy 切替後に旧 address を配列から削除して再度 rollout する。

DaemonSet または Node label の削除では、host の `egress0` は削除されない。Egress Gateway の使用を終了する場合は、
Policy、Egress 用 BGP advertisement、戻り経路の撤回を確認し、DaemonSet を削除して Pod の終了を待った後、既存の
`configure-egress-gateway-addresses.sh --action remove` を使用して所有済みの `egress0` を削除する。
通常の Egress 試験終了時は DaemonSet・ConfigMap・label・`egress0` を保持し、試験用 Policy・広報・Pod・サーバだけを撤去する。

address の手動変更を復旧するときは `configure-egress-interface-init.sh --context kind-adc-k02 --action restart` を使用する。
この処理は Node の再起動を行わない。移行用の追加 IP を残している間は、固定 IP 用の旧 helper の `check`／`remove` は使用しない。
