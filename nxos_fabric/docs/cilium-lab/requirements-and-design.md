# Cilium / Hubble / Tetragon 要件・設計台帳

この台帳は、初期構築からmultisite展開までの要件、設計判断、受入条件を一元管理する。
すべてを最初に確定するのではなく、[段階構築計画](build-plan.md)の各段階へ入る前に、
対象項目を`Ready`まで具体化する。構築後は実測結果を反映して`Validated`へ更新する。
Cilium Helm values の選択肢、選定値、選定理由、変更可否と変更手順は
[Cilium 設定パラメータ設計](cilium-configuration-parameters.md)を正本とする。

各項目を更新するときは、必要に応じて次を同じ行または補足節へ残す。

- 要求する状態と、その理由
- 採用する設定値または設計案
- 構築前提と依存項目
- 受入確認の方法
- 判断に使用した[参照URL](references.md)と確認日

## ステータス定義

| Status | 意味 |
|---|---|
| `Open` | 調査または判断が必要 |
| `Proposed` | 方針案があるが未確定 |
| `Ready` | 要件、設計値、構築前提、受入確認方法が確定 |
| `Validated` | labへ構築し、受入条件を満たすことを確認済み |
| `Rejected` | 今回は採用しない |
| `Deferred` | 後続の構築Stageへ延期 |

## 1. 構築成果と受入基準

| ID | 検討項目 | Status | 完了条件 |
|---|---|---|---|
| S-01 | single-site k02 の Cilium CNI | `Validated` | dual-stack の Pod 間、Service、外部疎通が成功することを 2026-08-30 に確認した |
| S-02 | Cilium LoadBalancer | `Ready` | VIP 割当、BGP 広告、外部到達、障害時 withdraw を確認する |
| S-03 | Hubble | `Validated` | allow／drop、DNS、HTTP、Service 通信を CLI／UI で識別できることを 2026-08-30 に確認した |
| S-04 | Cilium Network Policy | `Validated` | test namespace 内で L3／L4、DNS／FQDN、L7 HTTP、rollback の期待動作を `NP-00`～`NP-07` で確認した |
| S-05 | Tetragon | `Ready` | observe-only で process、file、network event を Pod 情報と関連付けて取得する |
| S-06 | multisite Cluster Mesh | `Ready` | k02／k03 間 Pod 通信、Global Service、API／dataplane partition、障害復旧を site 別 manifest と Test ID で確認する |
| S-07 | NX-OS 経路の実測確認 | `Ready` | Node 間および VIP 通信が想定した Leaf／DCI を通ることを capture または counter で確認する |
| S-08 | 再現性 | `Ready` | version lock、offline render、site 別 final profile、明示的な `--apply` を持つ収束 driver を作成済み。実環境での再実行結果だけを `Validated` とする |
| S-09 | Cilium Egress Gateway | `Ready` | 対象 Pod の外向き通信だけを指定 Gateway と Egress IP へ固定し、外部 server で送信元を確認する |
| S-10 | 最終状態への収束 | `Ready` | `singlesite-final`／`multisite-final` inventory と収束 driver を作成済み。Containerlab／kind lifecycle と validation workload を分離し、実環境での 2 回目実行結果だけを `Validated` とする |
| S-11 | Egress Gateway／Cluster Mesh 同時有効化 | `Deferred` | Stage 5 合格後に実験 profile を追加し、同一クラスタ内 Egress、cross-cluster 非選択、Mesh 通信の非干渉、rollback を確認する |

## 2. 基盤とkind

| ID | 検討項目 | Status | 確認内容 |
|---|---|---|---|
| K-01 | kind 実装 version | `Ready` | Containerlab `v0.78.2` 内蔵の kind library `v0.31.0` を使用する。外部 kind CLI はクラスタ作成に関与しない |
| K-02 | Node image | `Ready` | Kubernetes `v1.35.5` の `kindest/node` image を topology の共通値で digest 固定する。`kind load` を使う場合は kind CLI `v0.32.0` 以降で別途確認する |
| K-03 | host kernel | `Validated` | kernel `5.14.0`、必要な eBPF config、BTF、cgroup v2 を共通 preflight で確認し、2026-08-30 の post-install preflight は `FAIL=0` となった |
| K-04 | cgroup | `Validated` | host の cgroup v2、host／各 kind Node で異なる private cgroup namespace、Cilium の Socket LB 有効化を実測した |
| K-05 | kernel filesystem mounts | `Ready` | bpffs は Cilium auto-mount、tracefs／debugfs は kind 既定 mount を使用し、host `/proc` は初回 kind 作成時から `/procHost` へ read-only mount する |
| K-06 | resource sizing | `Validated` | single-site では構築後 `MemAvailable 43687 MiB`、OOM `0` を確認し条件付き合格とした。swap、CPU p95、host 全体の memory 差分は継続観測し、multisite は別途実測する |
| K-07 | Pod CIDR | `Ready` | k02 は `10.202.0.0/16`、`fd00:10:202::/56`、k03 は `10.203.0.0/16`、`fd00:10:203::/56` とし、Node mask は `/24`、`/64` とする |
| K-08 | Service CIDR | `Ready` | k02 は `10.102.0.0/16`、`fd00:10:102::/112`、k03 は `10.103.0.0/16`、`fd00:10:103::/112` とする |
| K-09 | kube-proxy | `Ready` | 初回から `kubeProxyMode: none` とし、k02 内で kube-proxy 構成との比較は行わない。site 別 Kind 設定へ反映済み |
| K-10 | API server endpoint | `Ready` | control-plane の動的 `eth0` IPv4 を構築時に取得して `k8sServiceHost` へ渡し、`k8sServicePort: 6443` とする。Fabric API は control-plane の Fabric IP を使用する |
| K-11 | Fabric CLI client | `Ready` | single-site／ADC は `adc-t1sv0101`、BDC は `bdc-t1sv0104` を専用 client とし、公式 CLI binary と site 別 kubeconfig を read-only bind して topology の `env.PATH` で有効化する。`adc-t1sv0102` は Egress 外部観測用に分離する |
| K-12 | CLI runtime準備 | `Ready` | site別version lockから公式kubectl/Cilium/Hubble binaryをSHA256検証し、Git管理外runtimeへ配置する |
| K-13 | Host CLI path | `Ready` | Containerlab 実行 host の site 別作業 shell で同じ `runtime/bin` を `PATH` の先頭へ追加し、profile 混在を避ける |
| K-14 | final profile | `Ready` | Egress Gateway を含む `singlesite-final` と Cluster Mesh を含む `multisite-final` を分ける。構築後の併用試験は `experimental-egress-clustermesh` とし、通常 profile に含めない |
| K-15 | convergence driver | `Ready` | check-only の offline render と、明示的な `--apply` による Node label／route、Helm、platform resource、wait、受入確認を依存順に実行する driver を作成済み。Containerlab／kind lifecycle と validation workload は対象外とする |
| K-16 | manifest境界 | `Ready` | Cilium／Tetragon は Helm values、platform CR と validation workload／Policy は Kustomize layer として実ファイル化し、旧 MetalLB directory の一括適用を禁止する |
| K-17 | CoreDNS upstream | `Ready` | Pod から到達確認できる IPv4 resolver を runtime 選定し、CoreDNS `forward` へ明示する。値は site 別の Git 管理外 runtime file に記録し、公開 manifest へ環境固有 IP を固定しない |

## 3. ノードネットワークとデータパス

| ID | 検討項目 | Status | 確認内容 |
|---|---|---|---|
| N-01 | Node InternalIP | `Ready` | API access は `eth0` に残し、Containerlab が bond/VLAN を構成した後に共通スクリプトで kubelet の dual-stack `--node-ip` を Fabric IP へ更新する |
| N-02 | Cilium node address | `Ready` | `CiliumNode.spec.addresses` と VXLAN tunnel endpoint が Node InternalIP の Fabric IP になることを構築後に確認する |
| N-03 | Cilium devices | `Ready` | `devices: "eth0,bond0.+"` とし、`nodePort.addresses` は k02 の `172.16.4.0/24`、`fd21:0:0:4::/64`、k03 の `172.16.5.0/24`、`fd21:0:0:5::/64` へ site 別に限定する |
| N-04 | local VLAN／VNI | `Ready` | k02 の VLAN `14`／`104` が VNI `10104` で `Up` となり、local port-channel と remote `nve1` の MAC 学習が成立することを実測した。Node-facing trunk は意図的に VLAN `1-4094` を許可したまま維持する |
| N-05 | static route | `Validated` | k03 の全 3 Node で `172.16.0.0/16` と `fd21:0:0::/48` の集約 route を `bond0.105` 側 Anycast Gateway `.1`／`::1` へ向け、`bond0.14` が存在せず、BDC Leaf の BGP endpoint ごとの host route が不要であることを確認済み |
| N-06 | MTU | `Ready` | Cilium／Pod `9000`、Node Fabric interface `9100`、NX-OS Node-facing／Fabric `9216` とする。k02 の Leaf running-config と全 Node へ適用し、interface error／drop `0`、Fabric API の IPv4／IPv6 HTTP `200` を確認した。PMTUD、fragment、Cilium／Pod MTU は Stage 1 で再試験する |
| N-07 | IPv6 | `Ready` | RA 依存を避けて static address／route を使用し、NDP、route、Service、BGP を IPv4 と分離して確認する |
| N-08 | datapath mode | `Ready` | 初期 Helm values は `routingMode: tunnel`、`tunnelProtocol: vxlan` とし、native routing を後続比較対象にする |
| N-09 | underlay family | `Ready` | 初期 tunnel underlay は IPv4 とし、IPv6 underlay は別試験とする |
| N-10 | Fabric 通過確認 | `Ready` | Node 送信経路、Leaf counter、必要に応じた packet capture を同一時刻で突き合わせる |
| N-11 | API management path | `Ready` | Cilium Agent の bootstrap は control-plane `eth0` IPv4 を自動取得して使用し、LoadBalancer VIP へ依存させない |
| N-12 | asymmetric routing | `Ready` | Fabric から到着した VIP 通信の戻りが `eth0` へ流れず、reverse path filter で drop されないことを確認する |
| N-13 | API fabric path | `Ready` | control-plane Fabric IP を API 証明書 SAN へ含め、TCP `6443` の secondary endpoint として公開する |
| N-14 | Fabric CLI path | `Ready` | ADC／BDC の専用 network-multitool から Fabric IP と route を使い分け、API／VIP への実経路を確認する |

## 4. Cilium CNI / IPAM

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| C-01 | Kubernetes IPAM | P0 | `Validated` | `ipam.mode: kubernetes` と Kind の明示 Pod CIDR により全 Node の Pod address が割り当てられることを確認した |
| C-02 | dual-stack endpoint | P0 | `Validated` | 全 Node で IPv4／IPv6 endpoint が Ready となり、same-node／cross-node の両 family で疎通することを確認した |
| C-03 | VXLAN | P0 | `Ready` | UDP `8472`、tunnel endpoint、MTU、Node 障害を確認する |
| C-04 | health endpoint | P0 | `Validated` | `cilium-health` で 3／3 Node の host／endpoint IPv4／IPv6 connectivity を確認した |
| C-05 | native routing | P2 | `Deferred` | Pod CIDRのNX-OS広告と戻り経路を含めて比較する |
| C-06 | masquerading | P1 | `Ready` | 初期 single-site values から BPF masquerading を有効化し、Pod 外向き IPv4／IPv6 の SNAT と送信元を確認する |
| C-07 | endpoint routes | P2 | `Deferred` | 初期 VXLAN 構成では無効を維持し、native routing 比較時に経路表への影響を評価する |
| C-08 | CiliumEndpointSlice | P2 | `Deferred` | Egress Gateway profile では無効を維持し、別 profile でのみ operator 負荷と Cluster Mesh との関係を評価する |

## 5. Service Load Balancer / BGP

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| L-01 | kube-proxy replacement | P0 | `Validated` | `kubeProxyMode: none` と `kubeProxyReplacement: true` で Socket LB、dual-stack ClusterIP、NodePort を確認した |
| L-02 | LB IPAM | P0 | `Ready` | site ごとに `infra` と `app` の non-overlap dual-stack pool を割り当て、selector、枯渇、競合、requested IP を確認する |
| L-03 | explicit LB class | P0 | `Ready` | `defaultLBServiceIPAM: none` と `io.cilium/bgp-control-plane` を使い、Cilium 対象 Service を明示する resource を作成済み |
| L-04 | BGP Control Plane v2 | P0 | `Validated` | single-site k02 で worker 2 Node だけを speaker とし、ADC BGR 2 台への IPv4／IPv6 合計 8 session が `established` となることを確認した。k03 は未実施 |
| L-05 | Service VIP 広告 | P0 | `Validated` | single-site k02 で `/26`／`/112` aggregate と Local Service exact route が Cilium、BGR RIB、EVPN Type-5 へ反映されることを確認した。Cluster Mesh API は未実施 |
| L-06 | ECMP | P0 | `Ready` | worker 2 Node の広告、NX-OS next-hop `2` 本、新規 flow の分散、片 Node 停止時の収束を確認する |
| L-07 | `externalTrafficPolicy` | P0 | `Ready` | 同じ backend を持つ `Cluster` と `Local` の Service を分け、広告 Node、source IP、backend 配置、障害動作を比較する |
| L-08 | SNAT／DSR | P1 | `Deferred` | 初期値は `snat` とし、LB／Egress の基礎合格後に DSR の dispatch、戻り経路、source preservation、MTU を別 profile で比較する |
| L-09 | Maglev | P1 | `Ready` | global `random` を維持し、Service annotation で限定した Maglev と分散、backend 変更時の connection churn を比較する |
| L-10 | graceful restart | P1 | `Ready` | 初期状態は無効とする。Agent-only 再起動では後続比較 profile とし、Node 本体の停止では selector から明示的に除外して route を withdraw する |
| L-11 | BGP policy attributes | P1 | `Ready` | explicit Service selector と Cluster Mesh API community k02 `65012:510`／k03 `65022:510` を設定し、Local Preference／MED は送信しない |
| L-12 | Pod CIDR広告 | P2 | `Deferred` | native routingフェーズでのみ有効化する |
| L-13 | L2 Announcements | P3 | `Deferred` | BGPを利用できないL2環境との比較用途に限定する |
| L-14 | BGP termination | P0 | `Ready` | k02 は ADC BGR で終端し、k03 は BDC Leaf の tenant VRF 専用 loopback で終端する。Anycast Gateway との BGP peering は行わない |
| L-15 | ASN allocation | P0 | `Ready` | ADC BGR `65010`、k02 `65012`、BDC 論理 BGR `65020`、k03 `65022` とし、BDC Leaf の Fabric ASN `65002` は変更しない |
| L-16 | BDC BGP endpoint | P0 | `Ready` | `172.16.253.101/32`、`172.16.253.102/32` と対応する IPv6 `/128` を Leaf 固有 endpoint とし、Cilium から 2 台の Leaf peer を手動指定する |
| L-17 | BGP import policy | P0 | `Ready` | 初期 Cilium aggregate `/26`／`/112`、hybrid の Cluster Mesh API exact route、`externalTrafficPolicy: Local` が生成する LB pool 内の exact route だけを許可する。Neighbor／AF ごとの `maximum-prefix 64` と eBGP `maximum-paths 4` を使用する |
| L-18 | DCI route export／import scope | P0 | `Ready` | 初期採用は `hybrid-clustermesh-only` とし、DCI には Cluster Mesh API exact route と Node segment だけを公開する。application aggregate と BGP endpoint は site-local とする |
| L-19 | Service VIP 経路集約 | P0 | `Ready` | 初回から Cilium `/26`／`/112` 送信元集約を使用する。`externalTrafficPolicy: Local` は公式仕様どおり exact route とし、aggregate との longest-prefix 選択を確認する。advertisement 前に worker 2 Node へ aggregate blackhole route を設定し、未割り当て VIP、path attribute、障害、rollback を確認する。不合格時は直接 BGP 終端集約へ切り替える |
| L-20 | BGP maintenance／経路退避 | P0 | `Ready` | worker は drain 後に `bgp-maintenance=planned-shut` で `65535:0` 付き backup path へ移し、session uptime、best path、FIB、traffic を確認してから `withdrawn` で切り離す。normal／planned-shut の 2 profile は Node 数に依存させず、NX-OS の経路選択点で `graceful-shutdown aware` を有効化する。ADC BGR／BDC Leaf は Graceful Shutdown／GIR 後に切り離す |

## 6. Egress Gateway

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| E-01 | feature prerequisites | P0 | `Ready` | `egressGateway.enabled`、BPF masquerading、kube-proxy replacement、CRD identity を初期 single-site values で有効化する |
| E-02 | single-site isolation | P0 | `Ready` | Cluster Mesh 用共通 values へ含めず、k02 専用 Helm overlay として管理する |
| E-03 | CES exclusion | P0 | `Ready` | `ciliumEndpointSlice.enabled: false` を維持し、Egress Gateway と CES を同時に有効化しない |
| E-04 | source selection | P0 | `Ready` | namespace `egress-probe` と Pod label `lab.cilium.io/egress-policy=selected` で対象と対象外を分離する |
| E-05 | destination selection | P0 | `Ready` | `172.16.0.0/24`、`fd21:0:0:1::/64` を対象とし、`adc-t1sv0101` の `/32`、`/128` を除外する |
| E-06 | Gateway selection／冗長化 | P0 | `Ready` | Cilium `1.20.1` の Policy は単一 `egressGateway` だけを持つ。初期は `gw-a` を選択し、計画切替時に `gw-b` profile へ Policy を更新する。hard failure では自動切替を前提にせず、検知と手動切替時間を測定する |
| E-07 | Egress IP／interface | P0 | `Ready` | Cilium は Egress IP を動的割り当てしない。Policy 適用前に運用者が `adc-k02-worker` へ `.31`／`::3:1`、`adc-k02-worker2` へ `.32`／`::3:2` を secondary address として設定し、IPv4／IPv6 の別 Policy で Gateway ごとの `egressIP` を指定する |
| E-08 | dual-stack SNAT | P0 | `Ready` | IPv4／IPv6 Policy を分離し、選択中 profile の単一 Gateway と site 固有 Egress IP を指定する。各 address family の destination、除外 CIDR、外部観測 source を個別に判定する |
| E-09 | policy delay | P0 | `Ready` | 新規 Pod への identity／policy 反映前に想定外 source IP で外へ出る時間を測定する |
| E-10 | failure／rollback | P0 | `Ready` | `gw-a` → `gw-b` の明示的 Policy 切替、Node hard stop、invalid Egress IP、Policy 削除を分ける。切替時は既存 connection 切断を許容し、新規 connection の復旧時間を測定する |
| E-11 | external evidence | P0 | `Ready` | `adc-t1sv0102` を外部観測 server とし、server log／capture、Cilium BPF map、Node capture、NX-OS counter を同一時刻で対応付ける |
| E-12 | SNAT capacity | P1 | `Proposed` | 同一 Egress IP／remote tuple の connection 数、NAT map saturation、許容閾値を resource 実測後に決める |
| E-13 | Cluster Mesh 同時有効化 | P1 | `Deferred` | Cluster Mesh の基本受入後、k02／k03 ごとに local Policy と local Gateway を構成し、cross-cluster Gateway を選択しないことを専用試験で確認する |

## 7. Hubble

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| H-01 | node-local Hubble | P0 | `Validated` | Agent の flow 取得と namespace／Pod／protocol／verdict filter を確認した |
| H-02 | Hubble Relay | P0 | `Validated` | Relay が Ready となり、3／3 Node の flow を集約できることを確認した |
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
| P-03 | DNS／FQDN policy | P0 | `Validated` | kube-dns allow、許可／非許可 FQDN、DNS 障害境界、Hubble DNS flow、FQDN cache を `NP-05` で確認した |
| P-04 | HTTP L7 policy | P0 | `Validated` | 許可 `POST` と非許可 `PUT` を分け、HTTP status と Hubble L7 verdict を `NP-06` で確認した |
| P-05 | Clusterwide policy | P1 | `Deferred` | namespaced policy 合格後、audit と例外設計を用意して共通 guardrail を評価する |
| P-06 | Cluster Mesh policy | P1 | `Deferred` | local policy と基本 Cluster Mesh 合格後、remote cluster／identity を使う allow／deny を確認する |
| P-07 | Host Firewall | P2 | `Deferred` | auditから開始し、管理経路を遮断しない手順を作る |
| P-08 | WireGuard | P2 | `Deferred` | 暗号化範囲、UDP 51871、二重encapsulation、MTUを確認する |

## 9. Tetragon

| ID | 機能 | 優先度 | Status | 評価内容 |
|---|---|---:|---|---|
| T-01 | kernel／BTF 互換性 | P0 | `Validated` | host kernel、BTF、cgroup v2、`/procHost`、`hostProcPath` の preflight と Tetragon 稼働を確認した |
| T-02 | DaemonSet 導入 | P0 | `Validated` | Cilium Ready 後に Tetragon `1.7.0` を observe-only で導入し、全 Node の Pod と Operator が Ready となることを確認した |
| T-03 | process exec | P0 | `Ready` | `starwars`／`tetragon-probe` 内の限定 command で binary、arguments、parent、Pod／namespace 情報を取得する |
| T-04 | file access | P0 | `Ready` | test Pod 内の専用 `/tmp/tetragon-lab-*` path だけを対象に read／write event とノイズ量を確認する |
| T-05 | network event | P0 | `Ready` | test Pod の `tcp_connect`／`tcp_close` と Hubble flow を timestamp、Pod、5-tuple で突き合わせる |
| T-06 | privilege event | P1 | `Ready` | lab 専用 non-production Pod で失敗する capability check を `cap_capable` により observe-only で取得し、host process を対象外にする |
| T-07 | TracingPolicy filter | P0 | `Ready` | namespace、Pod label、binary、argument の順に filter を追加し、対象 event と対象外ノイズの差を確認する |
| T-08 | event export | P1 | `Ready` | 初期は `tetra getevents -o compact` と JSON file を使用し、gRPC／metrics は保持期間と規模の実測後に判断する |
| T-09 | overhead | P0 | `Ready` | policy なし、限定 policy、event load の 3 点で CPU、memory、event drop を測り、構築後 memory gate と比較する |
| T-10 | Cilium 共存 | P0 | `Ready` | Tetragon 導入前後で Cilium status／connectivity、BPF filesystem、host mount、resource 競合がないことを確認する |
| T-11 | enforcement | P2 | `Deferred` | observe-only合格後にsigkill/override/denyの安全な対象を設計する |
| T-12 | failure safety | P1 | `Ready` | Tetragon DaemonSet 停止／再開時も CNI、ClusterIP、LoadBalancer 通信が継続することを確認する |

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

E-07 の専用 Egress IP は Cilium LB IPAM の pool から割り当てない。
Cilium Agent によって Node interface へ動的に追加されることもない。
明示した `egressIP` は Policy 適用前に Gateway Node の device 上へ実在する必要がある。
本ラボでは Node の primary address を流用せず、送信元識別と冗長化試験を容易にするため、次の secondary address を運用者が事前設定する。

| Gateway ID | Gateway Node／interface | IPv4 | IPv6 | Policy profile |
|---|---|---|---|---|
| `gw-a` | `adc-k02-worker`／`bond0.14` | `172.16.4.31/24` | `fd21:0:0:4::3:1/64` | `egress/gw-a`、初期選択 |
| `gw-b` | `adc-k02-worker2`／`bond0.104` | `172.16.4.32/24` | `fd21:0:0:4::3:2/64` | `egress/gw-b`、切替先 |

IPv4／IPv6 は別 Policy とし、それぞれの `spec.egressGateway` に 1 Node と 1 `egressIP` を指定する。
Cilium `1.20.1` は 1 Policy 内の複数 Gateway list を提供しない。selector が複数 Node に一致した場合も Node 名の
辞書順で最初の 1 台が選ばれるため、自動 HA として使用しない。本ラボでは同名 Policy を持つ `gw-a`／`gw-b`
Kustomize profile を排他的に管理し、計画切替では `kubectl diff -k` の後に選択先 profile を apply する。

Gateway を変更すると既存 Egress connection は切断される。lab では次を別 Test ID とする。

1. `gw-a` 使用中に `gw-b` profile へ明示的に切り替え、新規 connection の復旧時間を確認する。
2. `gw-a` Node を hard stop し、自動切替されないことと fail-closed／blackhole 時間を測定する。
3. 障害検知後に `gw-b` profile を適用し、手動復旧時間を測定する。

外部 firewall の allowlist は `.31`／`.32` と対応する IPv6 2 address を許可する。単一の floating Egress IP を
2 Node で共有する方式は Cilium Egress Gateway 単独では構成せず、ARP／NDP、重複 address、外部 routing を
含む別の HA 機構として扱う。

IPv4 Policy の Gateway 部分は次の形とし、IPv6 Policy は同じ selector で `egressIP` だけを対応する IPv6
address へ変更する。

```yaml
spec:
  egressGateway:
    nodeSelector:
      matchLabels:
        kubernetes.io/hostname: adc-k02-worker
    egressIP: 172.16.4.31
```

Node 再作成後も再現できるよう、secondary address の重複、対象 interface、prefix を検証してから
`ip address replace` を行う `scripts/cilium-lab/configure-egress-gateway-addresses.sh` を作成済みである。既存の
`configure-kubelet-node-ip.sh` は kubelet の `--node-ip` と restart だけを扱うため変更せず、Egress Gateway
profile だけが専用 script を呼び出す。Policy 適用前の gate は次のとおりとする。

```bash
docker exec adc-k02-worker ip -br address show bond0.14
docker exec adc-k02-worker ip route get 172.16.0.2 from 172.16.4.31
docker exec adc-k02-worker ip -6 route get fd21:0:0:1::102 from fd21:0:0:4::3:1
docker exec adc-k02-worker2 ip -br address show bond0.104
docker exec adc-k02-worker2 ip route get 172.16.0.2 from 172.16.4.32
docker exec adc-k02-worker2 ip -6 route get fd21:0:0:1::102 from fd21:0:0:4::3:2
```

Node network を変更した後は Cilium が新しい interface address を認識するまで待ち、Policy を再適用する。
`interface` だけを指定して device の最初の IPv4／IPv6 address を自動選択する方式も選べるが、Node primary
address と Egress address の役割が曖昧になるため、本ラボでは採用しない。

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
ip route get <control-plane-fabric-ip>
kubectl --request-timeout=10s get --raw='/readyz'
kubectl get nodes -o wide
cilium status --wait
hubble status -P
```

通常の Hubble 接続は `-P` による Kubernetes API port-forward とし、Relay を一時的に LoadBalancer 公開した
direct 接続は Fabric 公開試験として分離する。具体的な bind、PATH、kubeconfig 作成手順は
[Fabric 側 Kubernetes client と CLI 準備](client-tools.md)を正本とする。

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
[Network Policy／Tetragon 検証計画](network-policy-and-tetragon-test-plan.md)を正本とする。

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

`Ready` は構築済みを意味せず、設計値、前提、受入方法が確定した状態である。実行結果が合格した項目だけを
`Validated` とする。次の項目は初期構築または multisite 構築前に、追加の判断または実ファイル作成が必要である。

| ID | 残作業 | 必要時期 |
|---|---|---|
| K-02／K-06 | running Node image と memory gate を preflight で再確認し、不合格なら single-site 再作成前に解消する | Stage 1 前 |
| K-11 | topology へ CLI／kubeconfig bind と `env.PATH` を追記し、保守時間に対象 network-multitool を再作成する | Fabric CLI 試験前 |
| L-18 | `hybrid-clustermesh-only` に必要な NX-OS `10.5(4)` 用 route-map と device 別 candidate を、現行 config と統合して生成する | Stage 5 前 |
| E-12 | resource 実測後に SNAT capacity の負荷条件と許容閾値を決める | 性能試験前 |
| H-09／H-10 | metrics cardinality を実測し、必要なら export 先と保存期間を決める | 監視拡張前 |

`Deferred` の CES、endpoint routes、Clusterwide policy、MCS API、cross-cluster policy、Tetragon enforcement、
Egress Gateway／Cluster Mesh 同時有効化は、初期構築を止める未決事項ではない。
