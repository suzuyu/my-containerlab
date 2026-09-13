# Cilium / Hubble / Tetragon 要件・設計台帳

この台帳は、初期構築から multisite 展開までの要件、設計判断、受入条件を一元管理する。
すべてを最初に確定するのではなく、[段階構築計画](../build-plan.md) の各段階へ入る前に、
対象項目を `Ready` まで具体化する。構築後は実測結果を反映して `Validated` へ更新する。
Cilium Helm values の選択肢、選定値、選定理由、変更可否と変更手順は
[Cilium 設定パラメータ設計](cilium-configuration-parameters.md)を正本とする。

各項目を更新するときは、必要に応じて次を同じ行または補足節へ残す。

- 要求する状態と、その理由
- 採用する設定値または設計案
- 構築前提と依存項目
- 受入確認の方法
- 判断に使用した[参照URL](../reference/references.md)と確認日

## ステータス定義

| Status | 意味 |
|---|---|
| `Open` | 調査または判断が必要 |
| `Proposed` | 方針案があるが未確定 |
| `Ready` | 要件、設計値、構築前提、受入確認方法が確定 |
| `Validated` | 記載した環境・範囲で lab へ構築し、受入条件を満たすことを確認済み |
| `Rejected` | 今回は採用しない |
| `Deferred` | 後続の構築Stageへ延期 |

## 更新基準と最新照合

更新日：2026-09-13。実測は 2026-09-12〜13（記録日 2026-09-12）まで、設計判断は WireGuard 有効化時の MTU 変更合意までを反映する。
全体の進捗は [status](../status.md)、現行 MTU 設計は [architecture](../architecture.md#mtu-9100-plan)、
課題の状態・終了条件は [試験課題台帳](../test-issue-register.md#3-課題一覧) を正本とする。

- 特記のない実測結果と `Validated` は single-site `adc-k02` の記載範囲を指す。multisite の現在の構築・実測は未実施。
  `N-05` などに残す以前の k03 の個別確認を、新しい multisite 構成の受入完了とは扱わない。
- 一部だけ確認済みで受入項目が残る行は `Ready` を維持し、確認済み範囲と未実施条件を併記する。
  原因調査を要する項目は `Open` とする。課題台帳の `Workaround validated` と本台帳の `Validated` は区別する。
- connectivity 全体は lab CLI `v0.19.7-lab-flowfix.3` で **80/82 tests 成功、2 tests／3 actions 失敗**。
  試験用 Pod の旧 IP を修正した限定再試験は **1 test／6 actions 成功**。全体合格や WireGuard 有効化の確認を意味しない。
- `TI-005`／`TI-007`／`TI-008` は解消済み。`TI-001`／`TI-003` は回避策を確認済みで恒久対処は未完了。
  `TI-002`／`TI-004`／`TI-006` は `Open` を維持する。

| 結果資料 | この台帳で反映する範囲 |
|---|---|
| [09-12 設定照合・全体回帰・性能切り分け](../results/singlesite/2026-09-12/singlesite-regression-validation-2026-09-12.md) | 保存値・稼働値、CLI、BGP、全体／限定試験、性能の残課題 |
| [09-12 MTU・Fabric 経路の実装記録](../results/singlesite/2026-09-12/validation-status-2026-09-12.md) | Node `9150`、Cilium `9050`、Pod 経路 `9000`、InternalIP／VXLAN の Fabric 化 |
| [09-12 Egress 初期化の統合試験](../results/singlesite/2026-09-12/egress-interface-init-validation-2026-09-12.md) | DaemonSet 初回適用・設定変更・rollout、送信元・経路・新規 Pod |
| [09-06 までの検証結果](../results/singlesite/2026-09-06/validation-status-2026-09-06.md) | NP の既存合格、TG の観測範囲と証跡制約、Egress の異常系・計画切替 |

## 1. 構築成果と受入基準

| ID | 検討項目 | Status | 完了条件 |
|---|---|---|---|
| S-01 | single-site k02 の Cilium CNI | `Validated` | dual-stack の Pod 間、Service、外部基本疎通の 2026-08-30 合格を継承。09-12 の MTU／Fabric 修正後も基本通信を確認した。全体 connectivity は 80/82 tests 成功で未合格、性能は `TI-004` で継続する |
| S-02 | Cilium LoadBalancer | `Ready` | VIP 割当、BGP 広告、外部基本到達を確認済み。09-12 の回帰は LB 232/232 HTTP 成功。IPv6 Cluster LB は `TI-001` の checksum 回避策付きであり、障害時 withdraw、未割当 VIP、Forwarding／ECMP の受入は残る |
| S-03 | Hubble | `Validated` | allow／drop、DNS、HTTP、Service 通信を CLI／UI で識別できることを 2026-08-30 に確認した |
| S-04 | Cilium Network Policy | `Validated` | test namespace 内で L3／L4、DNS／FQDN、L7 HTTP、rollback の期待動作を `NP-00`～`NP-07` で確認した |
| S-05 | Tetragon | `Validated` | observe-only の process、file、network event と Pod 情報の対応を `TG-00`〜`TG-08` の定義範囲で確認済み。短時間負荷・停止復旧の範囲と原本ハッシュ未照合の制約は第 9 節に記載する |
| S-06 | multisite Cluster Mesh | `Ready` | k02／k03 間 Pod 通信、Global Service、API／dataplane partition、障害復旧の site 別 manifest と Test ID は準備済み。multisite 構築・実測は未実施 |
| S-07 | NX-OS 経路の実測確認 | `Ready` | single-site の Node 間・Egress 経路を Node／Leaf／BGR の capture・counter で照合済み。Fabric 内の遅延・欠落区間は `TI-004` で調査中。VIP の全経路・DCI の受入は未完了 |
| S-08 | 再現性 | `Ready` | version lock、offline render、site 別 final profile、収束 driver は作成済み。Egress helper の再 apply は成功したが、全体の新規構築・再実行の再現性は未確認。multisite の新規 Node への初回適用で確認する |
| S-09 | Cilium Egress Gateway | `Validated` | 対象 Pod・対象宛先だけが指定 Gateway の Egress IP となり、対象外・除外・CIDR 外と Policy 撤去後は通常送信元に戻ることを確認済み。基本機能の合格であり、性能・新規 Pod の初期 timeout・Node 障害系は第 6 節で継続する |
| S-10 | 最終状態への収束 | `Ready` | `singlesite-final`／`multisite-final` の inventory と収束 driver は作成済み。Egress 初期化 helper の統合と全体 check-only render は確認済みだが、全体 driver の実環境での適用・2 回目実行は未確認 |
| S-11 | Egress Gateway／Cluster Mesh 同時有効化 | `Deferred` | Stage 5 合格後に実験 profile を追加し、同一クラスタ内 Egress、cross-cluster 非選択、Mesh 通信の非干渉、rollback を確認する |

## 2. 基盤とkind

| ID | 検討項目 | Status | 確認内容 |
|---|---|---|---|
| K-01 | kind 実装 version | `Ready` | Containerlab `v0.78.2` 内蔵の kind library `v0.31.0` を使用する。外部 kind CLI はクラスタ作成に関与しない |
| K-02 | Node image | `Ready` | Kubernetes `v1.35.5` の `kindest/node` image を topology の共通値で digest 固定する。`kind load` を使う場合は kind CLI `v0.32.0` 以降で別途確認する |
| K-03 | host kernel | `Validated` | kernel `5.14.0-611.27.1.el9_7.x86_64` の eBPF config、BTF、cgroup v2 は初期 preflight で確認済み。IPv6 VXLAN checksum は `TI-001` の回避策が必要。kernel 更新は multisite 試験後に検討する |
| K-04 | cgroup | `Validated` | host の cgroup v2、host／各 kind Node で異なる private cgroup namespace、Cilium の Socket LB 有効化を実測した |
| K-05 | kernel filesystem mounts | `Ready` | bpffs は Cilium auto-mount、tracefs／debugfs は kind 既定 mount を使用し、host `/proc` は初回 kind 作成時から `/procHost` へ read-only mount する |
| K-06 | resource sizing | `Validated` | single-site では構築後 `MemAvailable 43687 MiB`、OOM `0` を確認し条件付き合格とした。swap、CPU p95、host 全体の memory 差分は継続観測し、multisite は別途実測する |
| K-07 | Pod CIDR | `Ready` | k02 は `10.202.0.0/16`、`fd00:10:202::/56`、k03 は `10.203.0.0/16`、`fd00:10:203::/56` とし、Node mask は `/24`、`/64` とする |
| K-08 | Service CIDR | `Ready` | k02 は `10.102.0.0/16`、`fd00:10:102::/112`、k03 は `10.103.0.0/16`、`fd00:10:103::/112` とする |
| K-09 | kube-proxy | `Ready` | 初回から `kubeProxyMode: none` とし、k02 内で kube-proxy 構成との比較は行わない。site 別 Kind 設定へ反映済み |
| K-10 | API server endpoint | `Ready` | control-plane の動的 `eth0` IPv4 を構築時に取得して `k8sServiceHost` へ渡し、`k8sServicePort: 6443` とする。Fabric API は control-plane の Fabric IP を使用する |
| K-11 | Fabric CLI client | `Ready` | single-site／ADC は `adc-t1sv0101`、BDC は `bdc-t1sv0104` を専用 client とし、公式 CLI binary と site 別 kubeconfig を read-only bind して topology の `env.PATH` で有効化する。`adc-t1sv0102` は Egress 外部観測用に分離する |
| K-12 | CLI runtime 準備 | `Validated` | single-site の site 別 version lock と保存 checksum に対し、09-12 の `prepare-tools.sh --check` で kubectl／Cilium CLI／Hubble CLI／Helm の一致を確認した。lab CLI は標準版と別管理。multisite は構築時に確認する |
| K-13 | Host CLI path | `Ready` | Containerlab 実行 host の site 別作業 shell で同じ `runtime/bin` を `PATH` の先頭へ追加し、profile 混在を避ける |
| K-14 | final profile | `Ready` | Egress Gateway を含む `singlesite-final` と Cluster Mesh を含む `multisite-final` を分ける。構築後の併用試験は `experimental-egress-clustermesh` とし、通常 profile に含めない |
| K-15 | convergence driver | `Ready` | 依存順を持つ check-only／明示 `--apply` の driver に Egress 初期化 helper を統合した。全体の offline render は成功、実環境は helper 単体の適用・再適用まで。Containerlab／kind lifecycle と validation workload は対象外 |
| K-16 | manifest境界 | `Ready` | Cilium／Tetragon は Helm values、platform CR と validation workload／Policy は Kustomize layer として実ファイル化し、旧 MetalLB directory の一括適用を禁止する |
| K-17 | CoreDNS upstream | `Validated` | Pod から到達確認した IPv4 resolver を runtime 選定し、CoreDNS の `forward` と 09-12 の check-only で一致した。公開 manifest に環境固有 IP は固定しない。`TI-003` の回避策であり、元の上流 DNS 問題の恒久解決とはしない |

## 3. ノードネットワークとデータパス

| ID | 検討項目 | Status | 確認内容 |
|---|---|---|---|
| N-01 | Node InternalIP | `Validated` | k02 全 3 Node の kubelet の dual-stack `--node-ip` と Kubernetes InternalIP を Fabric IP へ変更し、09-12 に再照合した。API bootstrap の管理側 `eth0` は維持。multisite の新規構築時の適用は未確認 |
| N-02 | Cilium node address | `Validated` | k02 の Cilium node address／VXLAN tunnel endpoint を Fabric IP へ変更して確認済み（`TI-005`）。旧 IP が残った hostNetwork 試験用 Pod も再作成し、限定 1 test／6 actions が成功した（`TI-008`） |
| N-03 | Cilium devices | `Ready` | `devices: "eth0,bond0.+"` とし、`nodePort.addresses` は k02 の `172.16.4.0/24`、`fd21:0:0:4::/64`、k03 の `172.16.5.0/24`、`fd21:0:0:5::/64` へ site 別に限定する |
| N-04 | local VLAN／VNI | `Validated` | k02 の VLAN `14`／`104`、VNI `10104` の Up と local port-channel／remote `nve1` の MAC 学習を確認済み。trunk の VLAN `1-4094` は維持し、09-12 に Leaf 4 台の Po11〜16 の LACP member と全 3 Node の 2 port aggregator を再照合した |
| N-05 | static route | `Validated` | k03 の全 3 Node で `172.16.0.0/16` と `fd21:0:0::/48` の集約 route を `bond0.105` 側 Anycast Gateway `.1`／`::1` へ向け、`bond0.14` が存在せず、BDC Leaf の BGP endpoint ごとの host route が不要であることを確認済み |
| N-06 | MTU | `Ready` | 現行値は Node Fabric NIC・bond・VLAN `9150`、Cilium 基準／Pod interface `9050`、Pod 経路 `9000`、Leaf L2／Fabric `9216`、管理側 `eth0` `1500`。k02 の適用・9000 byte 到達と 9001 byte のローカル拒否は確認済み（`TI-007`）。経路途中の PMTUD、WAN、性能受入は未完了。Leaf の最新変更の startup-config 保存も未実施 |
| N-07 | IPv6 | `Ready` | RA 依存を避けて static address／route を使用し、NDP、route、Service、BGP を IPv4 と分離して確認する |
| N-08 | datapath mode | `Validated` | k02 は `routingMode: tunnel`、`tunnelProtocol: vxlan` で稼働し、09-12 に Helm 明示値と稼働値を照合済み。native routing は後続比較対象、multisite は保存値のみ |
| N-09 | underlay family | `Validated` | k02 の Cilium VXLAN は外側 IPv4 で Fabric を通過することを確認済み。IPv6 underlay は別試験。WireGuard は未適用で、MTU の変更方針は `P-08` に記載する |
| N-10 | Fabric 通過確認 | `Ready` | 通常／`gw-a`／`gw-b` の Node Fabric・Leaf・BGR・外部サーバの capture と経路を照合済み。両 worker の管理側 `eth0` では対象 packet 0。Leaf uplink／Spine／peer-link 内の遅延・欠落箇所の確定は `TI-004` で継続する |
| N-11 | API management path | `Ready` | Cilium Agent の bootstrap は control-plane `eth0` IPv4 を自動取得して使用し、LoadBalancer VIP へ依存させない |
| N-12 | asymmetric routing | `Ready` | Fabric から到着した VIP 通信の戻りが `eth0` へ流れず、reverse path filter で drop されないことを確認する |
| N-13 | API fabric path | `Ready` | control-plane Fabric IP を API 証明書 SAN へ含め、TCP `6443` の secondary endpoint として公開する |
| N-14 | Fabric CLI path | `Ready` | ADC／BDC の専用 network-multitool から Fabric IP と route を使い分け、API／VIP への実経路を確認する |

## 4. Cilium CNI / IPAM

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| C-01 | Kubernetes IPAM | P0 | `Validated` | `ipam.mode: kubernetes` と Kind の明示 Pod CIDR により全 Node の Pod address が割り当てられることを確認した |
| C-02 | dual-stack endpoint | P0 | `Validated` | 全 Node で IPv4／IPv6 endpoint が Ready となり、same-node／cross-node の両 family で疎通することを確認した |
| C-03 | VXLAN | P0 | `Ready` | k02 の VXLAN endpoint の Fabric 化、外側 IPv4、MTU 境界は確認済み。UDP `8472` の経路は Fabric とし、Node 障害・再起動後の復旧は未検証。新規構築時の初期化を multisite で確認する |
| C-04 | health endpoint | P0 | `Validated` | `cilium-health` で 3／3 Node の host／endpoint IPv4／IPv6 connectivity を確認した |
| C-05 | native routing | P2 | `Deferred` | Pod CIDRのNX-OS広告と戻り経路を含めて比較する |
| C-06 | masquerading | P1 | `Validated` | k02 の BPF masquerading と通常外向き IPv4／IPv6 の送信元を確認済み。Egress 選択時の専用 IP と Policy 撤去後の通常送信元も照合した |
| C-07 | endpoint routes | P2 | `Deferred` | 初期 VXLAN 構成では無効を維持し、native routing 比較時に経路表への影響を評価する |
| C-08 | CiliumEndpointSlice | P2 | `Deferred` | Egress Gateway profile では無効を維持し、別 profile でのみ operator 負荷と Cluster Mesh との関係を評価する |

## 5. Service Load Balancer / BGP

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| L-01 | kube-proxy replacement | P0 | `Validated` | `kubeProxyMode: none` と `kubeProxyReplacement: true` で Socket LB、dual-stack ClusterIP、NodePort を確認した |
| L-02 | LB IPAM | P0 | `Ready` | site ごとに `infra` と `app` の non-overlap dual-stack pool を割り当て、selector、枯渇、競合、requested IP を確認する |
| L-03 | explicit LB class | P0 | `Ready` | `defaultLBServiceIPAM: none` と `io.cilium/bgp-control-plane` を使い、Cilium 対象 Service を明示する resource を作成済み |
| L-04 | BGP Control Plane v2 | P0 | `Validated` | k02 の worker 2 Node から ADC BGR 2 台への IPv4／IPv6 合計 8 session を確認し、09-12〜13 の最終照合でも Established を維持。k03 は未実施 |
| L-05 | Service VIP 広告 | P0 | `Validated` | single-site k02 で `/26`／`/112` aggregate と Local Service exact route が Cilium、BGR RIB、EVPN Type-5 へ反映されることを確認した。Cluster Mesh API は未実施 |
| L-06 | ECMP | P0 | `Open` | 広告・RIB／EVPN と Forwarding 表の差、BGR の exact route が 1 path に見える `TI-002` を継続調査する。next-hop 2 本、新規 flow 分散、片 Node 停止時の収束は合格にしない |
| L-07 | `externalTrafficPolicy` | P0 | `Ready` | Cluster／Local の基本疎通と後続 LB 回帰は成功。IPv6 Cluster の remote backend 応答には `TI-001` の VXLAN TX checksum off を使用する。source IP・広告・障害動作の全受入は未完了 |
| L-08 | SNAT／DSR | P1 | `Deferred` | 初期値は `snat` とし、LB／Egress の基礎合格後に DSR の dispatch、戻り経路、source preservation、MTU を別 profile で比較する |
| L-09 | Maglev | P1 | `Ready` | global `random` を維持し、Service annotation で限定した Maglev と分散、backend 変更時の connection churn を比較する |
| L-10 | graceful restart | P1 | `Ready` | 初期状態は無効とする。Agent-only 再起動では後続比較 profile とし、Node 本体の停止では selector から明示的に除外して route を withdraw する |
| L-11 | BGP policy attributes | P1 | `Ready` | explicit Service selector と Cluster Mesh API community k02 `65012:510`／k03 `65022:510` を設定し、Local Preference／MED は送信しない |
| L-12 | Pod CIDR広告 | P2 | `Deferred` | native routingフェーズでのみ有効化する |
| L-13 | L2 Announcements | P3 | `Deferred` | BGPを利用できないL2環境との比較用途に限定する |
| L-14 | BGP termination | P0 | `Ready` | k02 は ADC BGR で終端し、k03 は BDC Leaf の tenant VRF 専用 loopback で終端する。Anycast Gateway との BGP peering は行わない |
| L-15 | ASN allocation | P0 | `Ready` | ADC BGR `65010`、k02 `65012`、BDC 論理 BGR `65020`、k03 `65022` とし、BDC Leaf の Fabric ASN `65002` は変更しない |
| L-16 | BDC BGP endpoint | P0 | `Ready` | `172.16.253.101/32`、`172.16.253.102/32` と対応する IPv6 `/128` を Leaf 固有 endpoint とし、Cilium から 2 台の Leaf peer を手動指定する |
| L-17 | BGP import policy | P0 | `Ready` | LB aggregate と Local exact route の受信に加え、single-site の専用 Egress `/32`／`/128` の受信・撤回を確認済み。Neighbor／AF ごとの `maximum-prefix 64` と eBGP `maximum-paths 4` を採用する。Cluster Mesh API の hybrid 広告と multisite の受入は未実施 |
| L-18 | DCI route export／import scope | P0 | `Ready` | 初期採用は `hybrid-clustermesh-only`。DCI へ Cluster Mesh API exact route と Node segment を公開し、application aggregate と BGP endpoint は site-local とする。保存 config／candidate の静的準備までで DCI 実測は未実施 |
| L-19 | Service VIP 経路集約 | P0 | `Ready` | 初回から Cilium `/26`／`/112` 送信元集約を使用する。`externalTrafficPolicy: Local` は公式仕様どおり exact route とし、aggregate との longest-prefix 選択を確認する。advertisement 前に worker 2 Node へ aggregate blackhole route を設定し、未割り当て VIP、path attribute、障害、rollback を確認する。不合格時は直接 BGP 終端集約へ切り替える |
| L-20 | BGP maintenance／経路退避 | P0 | `Ready` | worker は drain 後に `bgp-maintenance=planned-shut` で `65535:0` 付き backup path へ移し、session uptime、best path、FIB、traffic を確認してから `withdrawn` で切り離す。normal／planned-shut の 2 profile は Node 数に依存させず、NX-OS の経路選択点で `graceful-shutdown aware` を有効化する。ADC BGR／BDC Leaf は Graceful Shutdown／GIR 後に切り離す |

## 6. Egress Gateway

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| E-01 | feature prerequisites | P0 | `Validated` | k02 の `egressGateway.enabled`、BPF masquerading、kube-proxy replacement、CRD identity を有効化済み。09-12 に single-site Egress を含む Helm 明示値と稼働値を照合した |
| E-02 | single-site isolation | P0 | `Ready` | single-site 専用 Helm overlay として管理し、k02 で稼働確認済み。`multisite-final` へ Egress を含めない設計で、multisite の実環境での分離確認は未実施 |
| E-03 | CES exclusion | P0 | `Validated` | k02 は `ciliumEndpointSlice.enabled: false` を維持し、Egress Gateway と CES を同時に有効化していないことを保存値・稼働値で照合した |
| E-04 | source selection | P0 | `Validated` | namespace `egress-probe` と Pod label `lab.cilium.io/egress-policy=selected` で分離し、selected だけ指定 Egress IP、unselected は通常送信元となることを確認済み |
| E-05 | destination selection | P0 | `Validated` | 対象 `172.16.0.0/24`／`fd21:0:0:1::/64`、`adc-t1sv0101` の明示除外、CIDR 外を個別に確認済み。09-12 の通常／`gw-a`／`gw-b` 各 12/12 HTTP で外部送信元が期待値に一致した |
| E-06 | Gateway selection／冗長化 | P0 | `Ready` | 単一 Gateway を選択し、`gw-a` → `gw-b` の明示切替後に新規接続の送信元が変わることを確認済み。hard failure の検知・手動切替時間は未測定。自動 HA・単一 IP 移動は前提にしない |
| E-07 | Egress IP／interface | P0 | `Validated` | k02 の対象 worker 2 台に初期化 DaemonSet と ConfigMap の `nodes.json` で `egress0` を設定。初回適用・同一設定の再 apply・設定変更と rollout・旧 IP 除去を確認済み。個別経路と所有 Node への戻り経路も確認。control-plane は非対象、新規 Node での初期化・再起動後維持は未検証 |
| E-08 | dual-stack SNAT | P0 | `Validated` | IPv4／IPv6 Policy を分離し、`gw-a`／`gw-b` の専用 Egress IP と外部観測 source を照合済み。09-12 は通常・両 Gateway の 9000 byte ICMP／UDP、低レート TCP も成功。性能全般の合格とはしない |
| E-09 | policy delay | P0 | `Open` | 新規 Pod の最新 3 回・240/240 HTTP は初回から指定 Egress IP で成功。以前の 239/240 成功時の初期 IPv4 timeout は原因未確定で `TI-006` を維持する。任意の起動条件での反映遅延・漏出の保証とはしない |
| E-10 | failure／rollback | P0 | `Ready` | Gateway selector 不一致・利用不能 IP の期待 drop と復旧、Policy 削除後の通常通信を確認済み。計画切替時の既存 TCP は両 family とも reset、新規接続は切替先で成功。Node hard stop・再起動後の復旧は未検証 |
| E-11 | external evidence | P0 | `Validated` | 外部サーバの request ID・送信元、Cilium BPF map、Node／Leaf／BGR の capture・経路・counter を照合済み。09-12〜13 の性能測定では Fabric の遅延・順序逆転と一部未観測区間を分離した。内部 queue・Pod socket 側の原因確定は `TI-004` で継続 |
| E-12 | SNAT capacity | P1 | `Deferred` | SNAT port 枯渇は未実施。先に `TI-004` の Fabric 遅延・順序逆転・欠落区間、Pod socket 未回収、TCP 再送を切り分ける。その後、同一 Egress IP／remote tuple の connection 数、NAT map saturation と許容閾値を具体化する |
| E-13 | Cluster Mesh 同時有効化 | P1 | `Deferred` | Cluster Mesh の基本受入後、k02／k03 ごとに local Policy と local Gateway を構成し、cross-cluster Gateway を選択しないことを専用試験で確認する |

## 7. Hubble

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| H-01 | node-local Hubble | P0 | `Validated` | Agent の flow 取得と namespace／Pod／protocol／verdict filter を確認した |
| H-02 | Hubble Relay | P0 | `Validated` | Relay Ready と 3/3 Node の flow 集約を確認済み。09-12 の全体試験開始時も接続成功。補助 observer で 1 event の欠落通知があり、全 capture の完全性を保証する判定とはしない |
| H-03 | Hubble UI | P1 | `Validated` | API 経由 port-forward で UI を表示し、`cilium-lab-policy` と `kube-system` の service map／flow を確認した |
| H-04 | verdict | P0 | `Validated` | Network Policy 試験で `FORWARDED` と `DROPPED` を traffic ごとに識別した。`ERROR`／`AUDIT` は後続試験とする |
| H-05 | L7 visibility | P0 | `Validated` | DNS、HTTP method／path／status、Policy verdict を `NP-05`／`NP-06` で確認した |
| H-06 | Service translation | P0 | `Validated` | Service frontend と worker 2 Node 上の backend Pod の対応を追跡した |
| H-07 | BGP／LB flow | P0 | `Ready` | 外部 client → VIP → Node → Pod を NX-OS 側観測と関連付ける |
| H-08 | Cluster Mesh | P1 | `Ready` | cluster 名、remote identity、共有 CA を cluster ごとに識別して確認する |
| H-09 | metrics | P1 | `Ready` | 初期 dynamic metrics で DNS、drop、TCP、HTTP、cardinality と resource 増分を評価する |
| H-10 | export／retention | P2 | `Deferred` | 初期は永続 export を行わず、single-site の event 量を測定後に file export または OpenTelemetry、保存期間を判断する |

## 8. Network Policy / Security

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| P-01 | Kubernetes NetworkPolicy | P0 | `Validated` | test namespace の default-deny、DNS allow、client → server allow、全 Policy rollback を `NP-01`～`NP-03`／`NP-07` で確認した |
| P-02 | CiliumNetworkPolicy | P0 | `Validated` | Service Account identity selector による L3／L4 allow／deny を `NP-04` で確認した |
| P-03 | DNS／FQDN policy | P0 | `Validated` | `NP-05` の許可／非許可 FQDN、DNS 障害境界、Hubble DNS flow、FQDN cache の合格を継承。CoreDNS は Pod 到達確認済み resolver を runtime 選定する `TI-003` の回避策付き。09-12 に forward の一致を再照合した |
| P-04 | HTTP L7 policy | P0 | `Validated` | 許可 `POST` と非許可 `PUT` を分け、HTTP status と Hubble L7 verdict を `NP-06` で確認した |
| P-05 | Clusterwide policy | P1 | `Deferred` | namespaced policy 合格後、audit と例外設計を用意して共通 guardrail を評価する |
| P-06 | Cluster Mesh policy | P1 | `Deferred` | local policy と基本 Cluster Mesh 合格後、remote cluster／identity を使う allow／deny を確認する |
| P-07 | Host Firewall | P2 | `Deferred` | auditから開始し、管理経路を遮断しない手順を作る |
| P-08 | WireGuard | P2 | `Deferred` | WireGuard 有効化時に Cilium の `MTU` を `9050` → `9145` へ変更する。外側 IPv4 VXLAN の `50` と WireGuard 見積もり `95` を含め、Pod 経路 MTU `9000` と通信を確認する。Node Fabric NIC・bond・VLAN は `9150` を維持。有効化までは `MTU: 9050`。kernel 対応、UDP `51871`、暗号化範囲・実経路・性能は実施時に確認する |

## 9. Tetragon

以下は [09-06 までの結果](../results/singlesite/2026-09-06/validation-status-2026-09-06.md) に記録した定義範囲を継承する。
09-12 に全 TG 試験を再実行したものではない。`Validated` の機能判定と証跡の完全性は別管理とし、
`TG-01` の対象側原本、`TG-02`〜`TG-05` などの転送元ハッシュ照合の制約を残す。

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| T-01 | kernel／BTF 互換性 | P0 | `Validated` | host kernel、BTF、cgroup v2、`/procHost`、`hostProcPath` の preflight と Tetragon 稼働を確認した |
| T-02 | DaemonSet 導入 | P0 | `Validated` | Cilium Ready 後に Tetragon `1.7.0` を observe-only で導入し、全 Node の Pod と Operator が Ready となることを確認した |
| T-03 | process exec | P0 | `Validated` | `TG-00` の built-in `process_exec`／`process_exit` と Pod metadata の対応、`TG-01` の custom `process_tracepoint` を確認済み。`TG-01` の対象側は提示された jq 出力が根拠で、完全な原本 JSON 照合には制約がある |
| T-04 | file access | P0 | `Validated` | `TG-02`／`TG-03` で試験 Pod の専用 path の write／read と対象外 path の抑制を確認済み。一部の転送元ハッシュ未照合は証跡上の残事項として保持する |
| T-05 | network event | P0 | `Validated` | `TG-04` で HTTP、`tcp_connect`／`tcp_close`、Hubble と外部 access log の対応を確認済み。accept 観測は範囲外。一部原本の転送元ハッシュ照合は未完了 |
| T-06 | privilege event | P1 | `Validated` | `TG-05` で `chown` の既存権限制約による失敗と capability event の対応を observe-only で確認済み。Tetragon enforcement の成功とはしない。原本ハッシュ照合には残事項がある |
| T-07 | TracingPolicy filter | P0 | `Ready` | `TG-01` の namespace の対象／非対象、`TG-02`／03 の path 抑制は確認済み。namespace・Pod label・binary・argument の全組み合わせの受入完了とはせず、未確認 filter 条件を残す |
| T-08 | event export | P1 | `Validated` | 定義した TG 試験で `tetra` の compact／JSON 観測を使用し、必要な結果を保存した。1 観測接続での短時間確認までで、永続 export、gRPC／metrics の規模・保存期間は未評価。原本完全性の制約は別記する |
| T-09 | overhead | P0 | `Ready` | `TG-06` は残存 `getevents` 整理後、1 観測接続・50 回の短時間負荷で成功。notify overflow 増分 0、Pod UID 不変・再起動 0。policy なし／限定 policy／負荷時の全容量評価と長期メモリ安定性は未完了 |
| T-10 | Cilium 共存 | P0 | `Ready` | 導入後の基本通信と `TG-08` の撤去後の built-in 観測・通信継続を確認済み。`TG-07` の停止復旧中は既存 IPv4 通信を確認。全体 connectivity、全資源競合、長期負荷の包括的受入は未完了 |
| T-11 | enforcement | P2 | `Deferred` | observe-only合格後にsigkill/override/denyの安全な対象を設計する |
| T-12 | failure safety | P1 | `Ready` | `TG-07` で Tetragon DaemonSet 停止・復旧中の既存 IPv4 通信と復旧後の観測再開を確認済み。停止中の IPv6 通信と無瞬断は保証していないため、全面合格とはしない |

## 10. Cluster Mesh / Multi-Cluster

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| M-01 | cluster name／ID | P0 | `Ready` | `adc-k02/2`、`bdc-k03/3` を導入時から固定する |
| M-02 | CIDR non-overlap | P0 | `Ready` | Pod／Service CIDR を IPv4／IPv6 とも分離する |
| M-03 | node reachability | P0 | `Ready` | Kubernetes InternalIP 間が NX-OS multisite 経由で dual-stack 到達することを確認する |
| M-04 | Cluster Mesh API | P0 | `Ready` | k02 `.14.10`／`adc-k02.mesh.cilium.io`、k03 `.15.10`／`bdc-k03.mesh.cilium.io` の dual-stack LoadBalancer、共通 CA、certgen、`authMode: cluster` を values／Service へ反映済み |
| M-05 | Pod-to-Pod | P0 | `Ready` | k02 ↔ k03 を IPv4／IPv6、TCP／UDP／ICMP で確認する |
| M-06 | Global Service | P0 | `Ready` | Cilium Global Service を MCS より先に構成し、cluster-local／remote backend 選択、local affinity、backend 消失時の fallback を確認する |
| M-07 | MCS API | P1 | `Deferred` | 初期は無効とし、Global Service 合格後に ServiceExport／Import、DNS、cluster failure を確認する |
| M-08 | cross-cluster policy | P1 | `Deferred` | local policy と基本 Cluster Mesh 合格後、cluster／namespace／identity 別の allow／deny を確認する |
| M-09 | Hubble multi-cluster | P1 | `Ready` | 共通 CA、cluster 識別、Relay 障害を確認する |
| M-10 | partition | P0 | `Ready` | API `2379/TCP` 断、Node 間 VXLAN `8472/UDP` 断、DCI 全断、片 cluster 停止を分ける。`cacheTTL: 10m` の保持／破棄と復旧後再同期を個別に確認する |
| M-11 | local Egress 非干渉 | P1 | `Deferred` | Egress Gateway 同時有効化後も cross-cluster Pod 通信、Global Service、remote identity 同期が維持されることを確認する |
| M-12 | Cluster Mesh API HA | P0 | `Ready` | 初期から 2 replica、worker 間 required anti-affinity、`bgp-speaker=true`、PDB `minAvailable: 1`、Service `ClientIP` affinity を使用し、この状態で resource を測定する |
| M-13 | BGP maintenance 連携 | P0 | `Ready` | worker planned-shut／drain 中も API VIP route を少なくとも 1 path 維持し、remote readiness、reconnect、full resync、Global Service を同時確認する |
| M-14 | state cache と障害面 | P0 | `Ready` | KVStoreMesh の last-known state と `cacheTTL` は control plane 断に対して動作する。dataplane-only 障害は別監視と別 Test ID で判定する |
| M-15 | namespace／policy scope | P0 | `Ready` | `defaultGlobalNamespace: false`、`policyDefaultLocalCluster: true` を明示し、`cilium-test` だけを annotation で global namespace にする |

## 11. 発展機能

以下は基礎、LB/BGP、Egress Gateway、Hubble、Cluster Meshが安定した後に扱う。

| ID | 機能 | Status | 目的 |
|---|---|---|---|
| A-01 | Gateway API | `Deferred` | HTTPRoute、TLS、gRPC、TCP/UDPとLB IPAM/BGPの統合 |
| A-03 | Bandwidth Manager | `Deferred` | Pod帯域annotation、EDT、BBR、遅延とthroughput |
| A-04 | XDP acceleration | `Deferred` | kind/コンテナ環境での制約を確認後に判断する |
| A-05 | native routing | `Deferred` | Pod CIDRをNX-OSへ広告し、VXLANとの経路・性能差を比較する |

## 12. Egress Gateway の address 管理

設計・設定・復旧の正本は [Egress IP・BGP 経路設計](egress-gateway-routed-design.md)、
実施コマンドは [Egress Gateway 試験手順](../tests/egress-gateway-test-plan.md) とする。

| Cluster | Gateway A の IPv4／IPv6 | Gateway B の IPv4／IPv6 | 保持先 |
|---|---|---|---|
| k02 | `172.16.24.1/32`／`fd21:0:0:24::1/128` | `172.16.24.2/32`／`fd21:0:0:24::2/128` | 各 Node の `egress0` |
| k03 | `172.16.25.1/32`／`fd21:0:0:25::1/128` | `172.16.25.2/32`／`fd21:0:0:25::2/128` | 各 Node の `egress0` |

Egress 専用 IPv4 `/24`・IPv6 `/64` は予約範囲とし、LB IPAM や Node connected subnet と重ねない。
Cilium による IP 自動割当は行わず、single-site k02 は [初期化 manifest](../../../nxos_singlesite/k8s_kind/k02/cilium/manifests/egress-interface-init/README.md) の
DaemonSet と ConfigMap の `nodes.json` で管理する。処理は DaemonSet の `STARTUP_SCRIPT` に記載し、
`quay.io/cilium/startup-script` を採用した Cilium chart と同じ digest に固定する。
`configure-egress-interface-init.sh` が所有 marker、既存 IP、依存コマンドを検査し、対象 label・manifest を収束させる。

- 対象は `nodes.json` に登録した worker 2 台で、対応する label を持つ Node に配置する。control-plane には配置しない。
- 初回 Pod 作成時と rollout による新しい Pod で設定する。新 IP が使用可能になってから旧 IP を除去する。
- ConfigMap だけを変更しても動作中の Pod には反映しない。helper は変更を検出して rollout する。
  通常稼働中は定期的なアドレス変更・修復を行わず、設定ずれの復旧は明示 restart を使用する。
- 初回適用・設定変更・再 apply は確認済みだが、ゼロからの Node 初期化は multisite 新規構築時に確認する。
  Node 再起動後のリンク復旧・設定維持は別の未検証事項として残す。

実際の送信 NIC は Fabric 側 NIC とし、Policy は `egressIP` を指定して `interface` を省略する。
Egress IP 変更で kubelet Node IP、BGP source address、LB 集約を変更しない。

戻り通信は SNAT した Node の NAT 状態に対応する必要がある。各 Node が固有の IP を広報し、NX-OS は個別経路を保持する。
`gw-a`／`gw-b` の Policy は排他的に適用し、切替時は新しい接続が `.1` → `.2` に変わることを確認する。
Cilium の複数 Gateway 機能とは分け、今回の試験では自動切替・単一 IP の移動・既存接続の引継ぎを前提にしない。

外部 firewall は使用する Gateway の専用 Egress IP を送信元として許可する。
BGP 広報は Policy の存在と自動連動しない。通常の試験後は Policy・試験用広報・Pod・サーバを撤去し、
個別・集約経路の撤回と LB 維持を確認する。初期化 DaemonSet・ConfigMap・label・`egress0` は常設として保持する。
完全撤去時だけ、Policy・広報・戻り経路の撤回後に DaemonSet を停止し、旧 helper の
`configure-egress-gateway-addresses.sh --action remove` で所有済み `egress0` を削除する。
BGP session の維持だけで合格にせず、外部サーバの `remote`、BPF map、RIB／FIB、LB 回帰を突き合わせる。
k03 は Stage 5 後の [実験 profile](../tests/egress-clustermesh-coexistence-test.md) に限り適用する。

## 13. DCI scope と経路集約の責務

L-18 は site 間へ公開する route scope、L-19 はその route を集約する地点を決める項目である。Cilium、直接
BGP 終端、DCI BGW の比較と合否基準は
[Cilium Service VIP 経路集約の比較設計](bgp-route-aggregation-design.md)を正本とする。

| 境界 | 主な責務 | 現在の方針 |
|---|---|---|
| Cilium → local BGP termination | Service 選択、VIP route、path attribute | 初回から Cilium `/26`／`/112` を広告し、hybrid では Cluster Mesh API exact route も広告する |
| local BGP termination | Cilium route の受信と Fabric への再広告 | Cilium 集約が不合格の場合の fallback 集約点とする |
| local Fabric | local Service route と Node segment の到達性 | 採用した aggregate または exact route を運ぶ |
| source／remote site BGW | DCI export／import の最終 safety boundary | prefix と site community を照合し、決定した scope 以外を拒否する |

Cilium 集約は Service 所有者に最も近く、k02／k03 の BGP 終端方式の違いを downstream へ持ち込まないため、
初期広告方式として採用する。ただし、現在の IPv4 `/26` は pool 外の `.0-.9` と `.51-.63` を含む。
IPv6 `/112` も常時すべての address が Service に割り当てられるわけではない。Cilium 公式文書は未割り当て
VIP を含む aggregate への traffic が routing loop になる既知の問題を明記している。このため、BGP resource
適用前に worker 2 Node へ aggregate blackhole route を設定し、negative test を初期受入条件にする。

また、1 cluster 1 aggregate だけでは Cluster Mesh API VIP と application VIP を DCI 境界で分離できない。
application VIP を site-local のまま維持する場合は、local Fabric 用 `/26`／`/112` に加えて Cluster Mesh API の
exact `/32`／`/128` と site community を Cilium から広告し、BGW で exact route だけを許可する hybrid を
試験する。hybrid が不合格なら exact route を維持するか、reachability scope ごとに整列した pool へ再設計する。
cluster の LB VIP range 全体を DCI 公開する `aggregate-all` を選ぶ場合だけ、単一 aggregate を DCI まで許可する。

`172.16.4.0/24`／`172.16.5.0/24` と対応する IPv6 Node segment は Cluster Mesh の VXLAN／health 用に
DCI 到達性を維持する。BGP endpoint loopback は site-local とし、Pod／Service CIDR は初期 VXLAN profile で
BGP 広告しない。

## 14. Fabric CLI client の選定

専用 image や sidecar は追加せず、既存 network-multitool の用途を次のように固定する。

| Site／役割 | Containerlab Node | 用途 |
|---|---|---|
| single-site／ADC CLI client | `adc-t1sv0101` | Fabric API endpoint、Cilium LoadBalancer VIP、Hubble への操作元 |
| multisite／ADC CLI client | `adc-t1sv0101` | k02 と remote k03 の Fabric／DCI 到達確認 |
| multisite／BDC CLI client | `bdc-t1sv0104` | k03 と remote k02 の Fabric／DCI 到達確認 |
| Egress 外部観測 server | `adc-t1sv0102` | Egress source IP の access log／capture。kubeconfig は配布しない |

CLI client には site 別 `runtime/bin` と `runtime/kubeconfig` だけを read-only bind する。`PATH` と
`KUBECONFIG` は topology の `env` で固定し、container image 内の `/usr/local/bin` は隠さない。host 側の
kubeconfig directory は `0700`、config は `0600` とし、Git へ含めない。実行中 container には bind 追加が
反映されないため、YAML 更新と container 再作成は保守時間に行う。

受入時は「CLI が起動する」だけでなく、送信元 site と Fabric route を確認する。

```bash
ip route get "${CONTROL_PLANE_FABRIC_IP:?対象 site の control-plane Fabric IP を設定する}"
kubectl --request-timeout=10s get --raw='/readyz'
kubectl get nodes -o wide
cilium status --wait
hubble status -P
```

通常の Hubble 接続は `-P` による Kubernetes API port-forward とし、Relay を一時的に LoadBalancer 公開した
direct 接続は Fabric 公開試験として分離する。具体的な bind、PATH、kubeconfig 作成手順は
[Fabric 側 Kubernetes client と CLI 準備](../runbooks/client-tools.md)を正本とする。

## 15. Network Policy／Tetragon の初期試験方針

### 15.1 Network Policy

初期試験では cluster-wide policy を使用せず、`cilium-lab-policy` namespace 内だけで次の順に確認する。

1. Policy なしの baseline 通信と Hubble `FORWARDED` を記録する。
2. Kubernetes NetworkPolicy で default-deny ingress／egress を適用し、既存 connection と新規 connection を分けて確認する。
3. kube-dns への UDP／TCP `53` と、明示した client → server の L3/L4 だけを許可する。
4. CiliumNetworkPolicy で Pod／namespace identity と Service Account selector を確認する。
5. FQDN policy で許可名、非許可名、TTL 更新、DNS 失敗を確認する。
6. HTTP L7 policy で許可 method／path と非許可 method／path を比較する。
7. 全 Policy を削除し baseline へ戻ることを確認する。

default-deny は lab namespace 外へ適用しない。各 test は通信結果、`kubectl describe`、Cilium policy status、
Hubble verdict を同じ Test ID で保存する。Clusterwide policy と Cluster Mesh policy は local namespaced
policy の合格後へ延期する。

具体的な Test ID、適用順、判断 command、合否条件、rollback は
[Network Policy／Tetragon 検証計画](../tests/network-policy-and-tetragon-test-plan.md)を正本とする。

判断 command の基本形は次のとおりとする。

```bash
kubectl -n cilium-lab-policy get networkpolicy,ciliumnetworkpolicy
kubectl -n cilium-lab-policy describe networkpolicy
cilium status --wait
hubble observe -P --namespace cilium-lab-policy --since 5m
```

### 15.2 Tetragon

Tetragon は初期から導入するが、試験は observe-only とし、次の順に範囲を広げる。

1. built-in process execution event で binary、arguments、parent、Pod／namespace metadata を確認する。
2. namespace、Pod label、binary で対象を絞った TracingPolicy を追加する。
3. test Pod 専用の `/tmp/tetragon-lab-*` に対する file read／write だけを観測する。
4. test Pod の `tcp_connect`／`tcp_close` event と Hubble flow を timestamp、Pod、5-tuple で照合する。
5. lab 専用 Pod で失敗する capability check を観測し、host process は対象外にする。
6. policy なし、限定 policy、event load の 3 点で CPU、memory、event drop を比較する。
7. Tetragon の停止／再開中も Cilium の CNI、ClusterIP、LoadBalancer 通信が継続することを確認する。

低水準の hook 名や argument index を独自に推測せず、採用する Tetragon version の公式 policy library／例を
取得して内容を review してから site 別 manifest として保存する。event に secret、token、kubeconfig 内容を
残さず、JSON log と capture は Git 管理外に保存する。enforcement は observe-only 合格後の別 profile とする。

判断 command の基本形は次のとおりとする。event 取得 command は短時間だけ実行し、試験 Pod の作成時刻を
記録して Hubble flow と照合する。

```bash
kubectl -n kube-system rollout status daemonset/tetragon
kubectl exec -n kube-system daemonset/tetragon -c tetragon -- tetra getevents -o compact
kubectl top pods -n kube-system --containers
cilium status --wait
```

## 16. 現時点で残る設計・成果物

single-site の確認済み範囲を維持し、未実施・原因調査中の項目を以下に残す。
構築順序と受入手順は [build-plan](../build-plan.md)、直近の優先順位は [status](../status.md) を参照する。

| ID | 残作業 | 必要時期 |
|---|---|---|
| S-01／C-03 | 累積 drop と今回の増分を区別して全体 connectivity の受入を継続する。限定再試験の成功で全体合格にしない | 次回全体受入 |
| N-10／E-11／E-12 | `TI-004` の Fabric 内の遅延・順序逆転・欠落区間、Pod socket 未回収、TCP 再送を切り分ける | 性能受入の前 |
| N-06 | 経路途中・WAN の PMTUD と追加カプセル化を検証する。Leaf の最新 MTU／LACP 変更の startup-config 保存は未実施 | 対象経路・操作を定めた受入時 |
| S-02／L-06／L-19／L-20 | `TI-002` の Forwarding／ECMP、未割当 VIP、計画退避・障害・広告収束を確認する | LB／BGP 全体受入 |
| E-09 | `TI-006` の初回 timeout の原因と再現条件を調べる。最新 240/240 成功だけで解消扱いにしない | 新規 Pod の追加確認 |
| E-06／E-10／E-12 | Node 障害系・SNAT port 枯渇は保留。実施条件と閾値を具体化する | 別途定める試験枠 |
| S-08／S-10／K-15／E-07 | multisite の新規 Node に topology・保存設定・manifest を順に適用し、初期状態からの構築と初期化を確認する。全体 driver の再実行も未確認 | multisite 構築時 |
| K-02／K-06／K-12 | multisite の running Node image、memory gate、client tools の version／checksum を実測する | multisite 構築時 |
| K-11／N-14 | Fabric CLI の topology 定義と稼働側の bind・PATH・kubeconfig 反映を再照合する。必要な container 再作成は操作単位を決める | Fabric CLI 試験前 |
| L-18／M-* | 保存済み candidate と実環境を照合し、Cluster Mesh／DCI の到達・広告・障害復旧を実測する | Stage 5 |
| K-03 | checksum 回避策を維持し、kernel 更新・恒久対処を検討する | multisite 試験後 |
| P-08 | WireGuard 有効化と同時に Cilium MTU を 9145 へ変更し、Node 9150 のまま Pod 経路 9000・暗号化・通信・性能を確認する | WireGuard 発展試験時 |
| T-03〜T-08 | TG の機能判定を保持し、一部原本・転送元ハッシュの完全性照合を補完する | 証跡補完時 |
| T-07／T-09／T-10／T-12 | 未確認 filter、長期負荷・資源競合、停止中の IPv6 と無瞬断の受入条件を具体化する | Tetragon 追加試験時 |
| H-09／H-10 | metrics cardinality を実測し、必要なら export 先と保存期間を決める | 監視拡張前 |

Node の再起動後のリンク自動復旧・設定維持は未検証で、新規構築の成功で代替しない。
`Deferred` の機能は初期構築を止める未決事項ではない。Egress Gateway／Cluster Mesh 同時有効化は
Stage 5 合格後の実験 profile に限定し、通常の `multisite-final` へ混在させない。
