# Cilium / Hubble / Tetragon ラボ検討

## 目的

このディレクトリは、`nxos_fabric` の kind クラスタを使った Cilium、Hubble、Tetragon の
要件、設計判断、段階的な構築順序、各段階の受入確認、判断根拠を整理するための作業文書である。

対象環境と展開順は次のとおりとする。

1. `nxos_singlesite` の `adc-k02` で基本機能を確認する。
2. `nxos_multisite` の `adc-k02` と `bdc-k03` で Cluster Mesh を確認する。

`adc-k01` は既存の MetalLB／FRR 試験を維持し、`adc-k02` と `bdc-k03` では MetalLB を
導入せず、Cilium LB IPAM、BGP Control Plane、eBPF Service Load Balancer を評価する。

## 文書の読み順

1. [要件・設計台帳](requirements-and-design.md)
2. [Cilium 設定パラメータ設計](cilium-configuration-parameters.md)
3. [パラメータ・アドレス割り当て台帳](parameter-and-address-allocation.md)
4. [構成設計と構成図](architecture.md)
5. [現環境から初期構築までの変更計画](current-environment-change-plan.md)
6. [リソース設計と preflight](resource-and-preflight.md)
7. [BGP 終端設計と設定変更案](bgp-config-change-proposal.md)
8. [Cilium Service VIP 経路集約の比較設計](bgp-route-aggregation-design.md)
9. [Cilium BGP 経路退避とメンテナンス設計](bgp-maintenance-and-route-drain.md)
10. [Cluster Mesh Fabric／DCI 境界設計](clustermesh-fabric-dci-and-acceptance.md)
11. [検証ワークロード設計](test-workloads.md)
12. [Network Policy／Tetragon 検証計画](network-policy-and-tetragon-test-plan.md)
13. [Egress Gateway／Cluster Mesh 同時有効化試験](egress-clustermesh-coexistence-test.md)
14. [Fabric 側 Kubernetes client と CLI 準備](client-tools.md)
15. [段階的な構築計画](build-plan.md)
16. [Stage 成果物台帳](stage-artifact-inventory.md)
17. [2026-09-06 single-site k02 検証ステータス](validation-status-2026-09-06.md)（[2026-08-30 の履歴](validation-status-2026-08-30.md)）
18. [試験課題台帳](test-issue-register.md)
19. [参照 URL 台帳](references.md)

Egress Gateway の実施時は [構築・試験手順](egress-gateway-test-plan.md) を使用する。
今回の接続先・配置パス・転送運用は [実際の試験環境：single-site k02](execution-environment-singlesite-k02.md) に分離し、
別環境へ流用するときは環境メモの設定値を置き換える。

connectivity 試験の検証用 CLI を再作成する場合は、
[公式ソース取得・修正パッチ適用・ビルド手順](cli-lab-flowfix-build.md) を使用する。
`v0.19.7-lab-flowfix.3` の修正コード、適用前後のハッシュ、変更範囲と判定上の制約を同梱する。

設計確認後に single-site の k02 を実際に構築する場合は、
[adc-k02 Cilium 初期構築手順](../../nxos_singlesite/k8s_kind/k02/cilium/README.md)に従う。
この実行手順には、Helm を含む CLI バイナリ準備、`PATH` と kubeconfig の設定、preflight、
静的 render、Cilium／Tetragon の導入順序を記載する。

## 現在の位置付け

- 状態: `Single-site validation in progress`
- 試験記録日: 2026-09-06（2026-09-07 未明の MTU 再試験を含めて整理）
- single-site `adc-k02` は Kubernetes `v1.35.5`、Cilium `v1.20.1`、Hubble、Tetragon `v1.7.0` の
  初期構築を完了した
- LB／BGP 基本通信、Network Policy `NP-00`～`NP-07`、Tetragon `TG-00`～`TG-08` の定義した観測範囲を確認した。
  IPv6 Cluster LB は checksum 回避策ありの条件付き合格。TG の一部原本・転送ハッシュには確認範囲の制約が残る
- single-site Egress は基本機能、除外・対象外、異常設定時の拒否、計画切替、MTU 修正後のサイズ境界が成功。
  高負荷性能、SNAT 枯渇、全体 connectivity 再受入、Fabric 経路設計と実測の差分は未完了
- 最新の適用範囲・判定・残課題は [2026-09-06 検証ステータス](validation-status-2026-09-06.md) を正本とする。
  [2026-08-30 のスナップショット](validation-status-2026-08-30.md) は当時の履歴として保持する
- multisite `adc-k02`／`bdc-k03` は config／manifest の静的確認まで。Cluster Mesh と DCI の実測は未実施である
- ADC Leaf 4 台の k02 Node-facing MTU／description 修正は startup-config へ保存済みである
- 追加の server 向け Leaf0103／0104 Po11 MTU 9216 は running-config と保存 config に反映済み。
  この追加変更の startup-config 保存は未実施であり、上記 Node-facing の保存履歴とは分ける
- 確定した設計値と segment 内の host assignment は
  [パラメータ・アドレス割り当て台帳](parameter-and-address-allocation.md)で管理する
- 実行時取得値、image digest、後続 Stage の BGP policy は該当する構築段階で確定する

## Version baseline

| Component | Assigned | 理由 |
|---|---|---|
| Containerlab 内蔵 kind library | `v0.31.0` | Containerlab `v0.78.2` が直接使用し、外部の kind CLI はクラスタ作成に関与しない |
| Kubernetes | `v1.35.5` | `v1.35.0` の scheduler と StatefulSet の regression を回避する。kubeadm configuration は Kubernetes `1.35` で推奨される `v1beta4` を使用する |
| Helm CLI | `v4.2.4` | Cilium `v1.20.1` chart の静的 render に使用し、schema validation に合格した |
| Cilium | `v1.20.1` | 1.20系の最初のパッチリリース。Cluster MeshやMCS API関連の修正を含む |
| Tetragon | `v1.7.0` | 現行リリース。最初はobserve-onlyで使用する |

kind Node image は tag だけでなく digest まで固定する。

```text
kindest/node:v1.35.5@sha256:ce977ae6d65918d0b58a5f8b5e940429c2ce42fa3a5619ec2bbc60b949c0ac95
```

この image は kind `v0.32.0` で公開された。Containerlab `v0.78.2` に内蔵される kind library は
`v0.31.0` であり、kind は release をまたぐ Node image の完全な互換性を保証していない。一方、公式の
必須更新事項は新しい Node image の containerd に対する `kind load` である。Kubernetes `1.35.x` では
kubeadm `v1beta4` が推奨され、`v1beta3` は deprecated である。このラボでは `v1.35.5` と `v1beta4` を
採用し、初回のクラスタ再作成で kubeadm、
3 Node join、registry pull を受入確認する。ローカル image を投入する試験を追加する場合は、host 側の
kind CLI `v0.32.0` 以降を使用する。

## 構築方針

- 構築段階ごとに「要件・設計 → 設定作成 → 事前検証 → 構築 → 受入確認 → As-built更新」を完結させる。
- 1段階で追加する主要機能は1つのまとまりに絞る。
- k02は最初からkube-proxy-free Ciliumで構築し、LB IPAM/BGP追加時のクラスタ再作成を避ける。
- Stage 2 は inbound の LB IPAM／BGP と outbound の Egress Gateway を別変更として構築する。
- 疎通結果だけでなく、想定したNX-OS fabricを通ったことを確認する。
- 初期構築では Cilium の Ready を待ってから同じ手順内で Hubble／Tetragon まで導入する。
- 試験アプリと TracingPolicy／Egress policy は基盤の合格後に追加する。
- Tetragonは観測から始め、enforcementは別の構築段階にする。
- single-siteで合格した設定だけをmultisiteへ展開する。
- 段階構築と最終状態への収束は同じHelm valuesとKubernetes resourceを共有し、適用順序だけをprofileで切り替える。
- 最終状態の起動でも既存`manifest/`全体を一括適用せず、Cilium/TetragonのHelm releaseと依存順を持つresource layerを分離する。
- 検証workloadはplatformのfinal profileと分離し、試験時にvalidation profileとして適用・削除する。
- `stable` URLだけに依存せず、採用バージョンと確認日を[参照URL台帳](references.md)へ残す。
- 実測結果、失敗結果、system dumpの保存先は公開文書と分離し、`operations/`や`logs/`をGitへ含めない。

## 主要な設計判断

| ID | 論点 | 初期方針 |
|---|---|---|
| D-01 | Kubernetes Node `InternalIP` | Containerlab の Fabric NIC 構築後に kubelet `--node-ip` を更新し、Docker 管理用 `eth0` への迂回を防ぐ |
| D-02 | 初期datapath | VXLANから開始し、native routingは後続比較試験にする |
| D-03 | kube-proxy | 初回からkind `kubeProxyMode: none`とCilium `kubeProxyReplacement: true`を使用する |
| D-04 | LoadBalancer | 初回Cilium導入時にeBPF Service LBとBGP機能を有効化し、同一クラスタへLB IPAM/BGP resourceを追加する |
| D-05 | Cluster Mesh API 公開 | k02 は `.14.10`、k03 は `.15.10` の固定 dual-stack Cilium LoadBalancer VIP を使用する |
| D-06 | Hubble CA | multisiteでcluster-wide観測する場合は共有CAを検討する |
| D-07 | Tetragon enforcement | 初期対象外。observe-onlyのノイズと負荷を確認後に判断する |
| D-08 | dual-stack | 維持する。ただしIPv4とIPv6を別々の合格項目として扱う |
| D-09 | 複数NIC | `eth0`を管理/API、`bond0.<VLAN>`をNode InternalIP、VXLAN、BGP、Service公開に使用する |
| D-10 | Hubble UI公開 | 通常は`eth0`経由のport-forward、fabric確認時だけCilium LoadBalancer VIPで一時公開する |
| D-11 | local VLAN | leafごとにVLAN IDが異なっても同じL2 VNIなら許容し、VNI、ARP/NDP、MTUを受入確認する |
| D-12 | APIの同時公開 | 管理endpointをprimaryとして維持し、control-plane Fabric IPを証明書SANへ含めたsecondary endpointにする |
| D-13 | Fabric側CLI client | 対象network-multitoolへkubectl/Cilium/Hubble binaryとkubeconfigをread-only bindする |
| D-14 | CLI配布 | 独自imageを作らず、site別version lockに従い公式binaryとchecksumをGit管理外runtimeへ準備する |
| D-15 | Egress Gateway | Stage 2 を inbound の 2A と outbound の 2B に分ける。通常の multisite 構築では Cluster Mesh と分離し、Stage 5 合格後だけ公式サポート外の同時有効化試験を行う |
| D-16 | 最終状態への収束 | 段階構築と同じ宣言的部品をprofileから順序付きで適用し、`singlesite-final`と`multisite-final`を分離する |
| D-17 | BGP 終端 | `adc-k02` は `adc-bgrt0101/0102`、`bdc-k03` はメモリ制約を考慮して `bdc-lfsw0101/0102` の tenant VRF 専用 loopback で終端する |
| D-18 | ASN と BGP endpoint | ADC BGR は `65010`、k02 は `65012`、BDC の論理 BGR は `local-as 65020`、k03 は `65022` とし、BDC endpoint は `172.16.253.0/24` と `fd21:0:0:253::/64` から割り当てる |
| D-19 | MTU | Cilium／Pod は `9000`、Node Fabric interface は `9100`、NX-OS は `9216` とする |
| D-20 | Cluster DNS | k02／k03 とも `cluster.local`、MCS は `clusterset.local`、Cluster Mesh API domain は `mesh.cilium.io` とする |
| D-21 | Cilium API bootstrap | control-plane `eth0` IPv4 を runtime values へ生成し、全 Node から `/livez` を確認してから Helm へ渡す |
| D-22 | BGP speaker | cluster は 3 Node とし、`bgp-speaker=true` の worker 2 Node だけで BGP session を形成する |
| D-23 | Resource gate | single-site 実行ホストで初期構築前 `8192 MiB`、構築後 `4096 MiB` の `MemAvailable` を最低条件にする |
| D-24 | Egress Gateway 冗長化 | Cilium `1.20.1` の単一 `egressGateway` に合わせ、`gw-a`／`gw-b` の排他的 profile を明示的に切り替える。自動 HA は前提にせず、既存 connection 切断を許容して新規 connection の手動復旧時間を確認する |
| D-25 | Service VIP 経路集約 | 初回から Cilium `/26`／`/112` 送信元集約を使用する。BGP resource 適用前に worker 2 Node へ aggregate blackhole route を設定し、未割り当て VIP の loop、DCI 公開 scope、障害／rollback を受入確認する。不合格時は直接 BGP 終端で集約する |
| D-26 | BGP maintenance | worker は Node 数に依存しない normal／planned-shut の 2 profile と `bgp-maintenance` label で soft drain してから withdraw する。NX-OS の経路選択点で `graceful-shutdown aware` を有効化する。router／Leaf は Graceful Shutdown／GIR 後に切り離し、同じ role の 2 台同時停止を禁止する |
| D-27 | Cluster Mesh 可用性 | 初期から API 2 replica、worker 間 required anti-affinity、PDB `minAvailable: 1`、Service `ClientIP` affinity を使用し、この状態で resource を測定する。global namespace は `cilium-test` へ限定し、API 断と Node dataplane 断を別 Test ID で判定する |

## 更新方法

各構築段階で、次の順に文書と設定を更新する。

1. `requirements-and-design.md` の対象項目を調査し、要件、設計値、受入条件を `Ready` にする。
2. `parameter-and-address-allocation.md` と `architecture.md` の割り当て、論理構成、物理経路を一致させる。
3. `build-plan.md` の対象段階に従い、設定と manifest を作成して静的検証する。
4. ユーザーが対象と操作を明示した後に構築し、段階内の受入確認を実施する。
5. 実測した構成を As-built として文書へ反映し、該当項目を `Validated` にする。
6. 参照した公式資料を `references.md` へ確認日付きで追記する。

Cilium 設定パラメータを追加・変更するときは、
[Cilium 設定パラメータ設計](cilium-configuration-parameters.md)の一覧表と項目別の節を同時に更新する。
項目別の節には、項目の意味、選択肢、採用 Cilium version の既定値、本ラボでの初期設定、選定理由、後からの変更可否、
変更方法、変更時の影響と確認事項を記録する。

Egress のアドレス割当と個別経路は [Egress 専用 IP・BGP 経路設計](egress-gateway-routed-design.md) を参照する。
