# k03 の導入と Cluster Mesh 接続確認

## 結論

2026-09-13、clab02 の CDC 除外版で `bdc-k03` を導入し、`adc-k02` との
Cluster Mesh 接続と双方向の基本通信を確認した。
両クラスタの Cilium は OK、各 agent 3/3・KVStoreMesh 2/2 が相手サイトへ接続した。
直接 Pod 通信 16/16、Global Service 通信 8/8、外部から k03 LB への HTTP 12/12 が成功した。
いずれも IPv4／IPv6 を含む。障害復旧・性能・全体 connectivity の受入完了とはしない。

## 適用した設定

| 対象 | 最終設定・確認 |
|---|---|
| k03 Node | 3/3 Ready。Fabric InternalIP を control-plane `172.16.5.11`／`fd21:0:0:5::1:1`、worker `172.16.5.21`／`fd21:0:0:5::2:1`、worker2 `172.16.5.22`／`fd21:0:0:5::2:2` に再適用 |
| k03 Cilium | chart `1.20.1`、revision 2 deployed。`00-base.yaml`、`10-observability.yaml`、`20-multisite-clustermesh.yaml` と生成 API values を適用 |
| k03 API bootstrap | control-plane 管理 IP `172.18.0.9:6443`、全 Node の `/livez` 確認後に生成 |
| CA | k03 の初回 Cilium install 前に k02 の `cilium-ca` を共有。導入後にも fingerprint 一致を確認 |
| k02 更新 | Cilium revision 3 deployed。Mesh の固定 VIP による名前解決と API 更新方式を反映 |
| Mesh API | 各サイト 2 replica、別 worker に配置。PDB `minAvailable: 1`、Service affinity `ClientIP` |
| Mesh API VIP | k02 `172.16.14.10`／`fd21:0:0:14:0:0:1:10`、k03 `172.16.15.10`／`fd21:0:0:15:0:0:1:10` |
| k03 LB／BGP | pool・BGP CR・planned-shut profile・Mesh API Service を適用。maintenance label は未設定。両 worker から BDC Leaf 2 台へ IPv4／IPv6 計 8/8 Established |
| k03 集約用経路 | worker 2 台に `172.16.15.0/26` と `fd21:0:0:15:0:0:1:0/112` の blackhole route、metric `42760` |
| CoreDNS | Pod から検証した upstream `192.168.129.254` に変更し、Cluster DNS 経由の外部名解決も成功 |
| Tetragon | k03 chart `1.7.0`、revision 1 deployed、agent 3/3、operator 1/1。observe-only |
| Hubble | k03 Relay Ready。両サイトの Hubble が 6/6 Node に接続。UI は設計どおり k02 のみ |
| MTU | Node Fabric `9150`、Cilium 基準 `9050` を維持。BDC Leaf の k03 向け Po14〜16 を `9216` に修正 |
| checksum 回避策 | k03 の両 worker は `cilium_vxlan tx-checksum-ip-generic: on` を維持。state／timer は未作成 |

設定元は `nxos_fabric/nxos_multisite/k8s_kind/k03/cilium/` の values／resources と
`k03/tetragon/values/00-observe-only.yaml`。
Egress Gateway、WireGuard、MCS API、Tetragon enforcement は有効化していない。

## 導入中に修正した問題

### Node IP と kubeconfig

k03 の kubelet は管理 IP を使用していたため、既存 `configure-kubelet-node-ip.sh` で
Fabric IPv4／IPv6 を設定して kubelet のみを再起動した。Node 再起動は行っていない。
deploy 時の設定が未反映となる原因は k02 と同様に未特定。

専用 kubeconfig は control-plane 内の管理用設定から mode `600` で作成した。
初回の結合時は k02／k03 の認証エントリ名が同じで認証に失敗したため、k03 側のユーザー名を
`bdc-k03-admin` に分離した。API の host 側公開 port は `41233`。

### Mesh の名前解決

固定 values は FQDN を `address` に指定していたが、対応する DNS レコードがなく
`no such host` となっていた。両サイトの `20-multisite-clustermesh.yaml` を
`clustermesh.config.clusters[].ips` による固定 IPv4／IPv6 VIP 指定へ変更した。
chart が生成する host alias を使用し、FQDN と共通 CA による mTLS を維持した。
通常の Pod／ホスト向け DNS レコードを追加したわけではない。

### Mesh API の更新停止

worker 2 台に required anti-affinity で 2 replica を配置した状態で、既定の
`maxSurge: 1`／`maxUnavailable: 0` が追加 Pod の配置先を待っていた。
`maxSurge: 0`／`maxUnavailable: 1` に修正し、1 Pod を残して順次更新した。
両サイトの保存 values と Helm release に反映済み。PDB のみでは Deployment 更新時の可用性を制御しない。

相手サイト完成前に `cilium status --wait` を待つ手順も、LB／BGP の投入へ進めなくなるため、
README の基盤導入待ちを Cilium DaemonSet と Mesh API Deployment の rollout 確認に変更した。
Mesh 接続は両サイトの VIP／経路が揃ってから判定する。

### BDC Leaf の MTU 1500

Leaf0101／0102 の Po14・15・16 は実効 MTU `1500` だった。
ARP／ND と TCP 接続は可能だったが、kubelet への TLS ClientHello が `1546` byte となる通信で
timeout が発生し、Pod の exec／logs と DNS 設定の確認が進まなかった。

ユーザーの許可を得て、両 Leaf の対象 Po に `mtu 9216` を投入した。
member Ethernet1/4〜6 も `9216` へ反映され、Po はすべて up、LACP member は `P`、
vPC consistency は success。修正後は同じ TLS 接続で HTTP 応答を取得でき、DNS 試験も成功した。

`configs/as-equals/` と `configs/as-changes/` の両 Leaf 保存 config にも反映した。
導入時は running-config とリポジトリ内の config へ反映し、`write memory` は未実施だった。
同日の後続依頼で両機の startup-config へ保存し、Po14〜16 の `mtu 9216` も照合済み。
[後続の保存操作](checkpoint.md#後続の-push-と機器への保存) を参照する。

## 実通信と状態確認

| 試験 | 結果 |
|---|---|
| k03 導入後 preflight | PASS 78、WARN 0、FAIL 0。host／Node の検査であり、Leaf MTU の検査を代替しない |
| Mesh 接続 | k02 → k03、k03 → k02 とも agent 3/3、KVStoreMesh 2/2 connected |
| Cilium 状態 | 両クラスタ OK。導入前の remote cluster error は解消 |
| サイト間 Pod HTTP | 2 方向 × source worker 2 台 × destination worker 2 台 × IPv4／IPv6、16/16 成功 |
| Global Service HTTP | 2 方向 × source worker 2 台 × IPv4／IPv6、8/8 成功。`affinity: remote` とし、応答のクラスタ名でも相手サイトを確認 |
| 外部 k03 LB HTTP | ADC の `adc-t1sv0101` から k03 の backend 2 台 × IPv4／IPv6 × 3 回、12/12 成功 |
| IPv6 LB checksum | 外部 client で受信した TCP 26 packet が correct、不正 0 |
| CA | 両クラスタの SHA-256 fingerprint が一致 |
| Cluster health | 両クラスタで 6/6 reachable |
| BGP | 各クラスタ 8/8 Established |

一時試験 namespace は両クラスタの `cilium-mesh-bootstrap-check`。
Global Service 用の namespace／Service annotation を付け、backend と client を各 worker に固定した。
本番相当の workload や既存 namespace は使用していない。

今回の checksum 判定は上記経路・設定の範囲に限る。
大きな payload の MTU 境界、継続負荷、Policy、サイト断・API Pod 障害・経路退避、
Global Service の local 優先／remote fallback は未受入。
Node の無介入での初期化再現性と、k01／k02 の初回 ARP／ND 問題も残る。

## 資源と一時リソース

導入前の MemAvailable は約 `17.2 GiB`、試験 Pod を含む最終確認時は約 `11.5 GiB`。
swap 使用は `0`。全体 connectivity や障害試験の追加 workload を展開する前に再測定する。

一時 namespace の削除は当初、自動承認レビューで停止したが、その後ユーザーの承認を得て
両クラスタの `cilium-mesh-bootstrap-check` を撤去した。中断した DNS 試験 Pod も保存前には存在しない。
UI 用の `cilium-test` は保持した。撤去後の Mesh／BGP 確認は [保存時点の記録](checkpoint.md) を参照する。

## 操作環境

実施ホストで継続操作する場合は専用 kubeconfig を結合する。
再構築後は API 公開 port と認証情報を作り直す。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_multisite"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
export KUBECONFIG_K02="${LAB_ROOT}/k8s_kind/k02/cilium/runtime/kubeconfig-k02"
export KUBECONFIG_K03="${LAB_ROOT}/k8s_kind/k03/cilium/runtime/kubeconfig-k03"
export KUBECONFIG="${KUBECONFIG_K02}:${KUBECONFIG_K03}"
export KUBE_CONTEXT_K02="kind-adc-k02"
export KUBE_CONTEXT_K03="kind-bdc-k03"
cilium clustermesh status --context "${KUBE_CONTEXT_K02}"
cilium clustermesh status --context "${KUBE_CONTEXT_K03}"
```

## 証跡

Git 管理外の `nxos_fabric/nxos_multisite/operations/cilium-lab/2026-09-13/k03-mesh-install/` に
導入／更新ログ、CA 照合、名前解決の失敗、DNS 再試験、preflight、Mesh／BGP／Hubble 状態、
一時 manifest、HTTP 結果、受信 capture、メモリ値を保持する。
Helm render や kubeconfig は秘密情報を含み得るため公開しない。
