# 段階的な構築計画

## 1. 方針

試験を独立した後工程にはせず、動作可能な構成を一段ずつ積み上げる。各段階で要件と設計を
必要な範囲まで具体化し、設定作成、構築、受入確認、As-built更新までを完結させる。

```mermaid
flowchart LR
    S0["Stage 0\n初期要件・基本設計"] --> S1["Stage 1\n初期 platform 構築"]
    S1 --> S2["Stage 2A\nLB IPAM・BGP"]
    S2 --> S2B["Stage 2B\nEgress Gateway"]
    S2B --> S3["Stage 3\nHubble・Policy 動作確認"]
    S3 --> S4["Stage 4\nTetragon 動作確認"]
    S4 --> S5["Stage 5\nmultisite Cluster Mesh"]
    S5 --> S6["Stage 6\n構築後の互換性・発展試験"]
```

各 Stage は前段の As-built 構成を出発点とする。k02 は初回から kube-proxy-free Cilium で作成し、
LB IPAM／BGP feature、single-site Egress Gateway feature、Hubble、Tetragon を初期 platform 構築に含める。
依存順序は維持し、Cilium Ready 後に LB／BGP resource と Tetragon release を導入する。Stage 2～4 は
基盤を後付けする段階ではなく、試験アプリ／policy を追加して機能ごとの合否を確定する確認段階とする。
未解決事象を残したまま、原因を増やす主要機能を追加しない。互換性比較や破壊的変更が必要な
発展機能だけを別profileとして扱う。

## 2. 各Stageの進め方

```mermaid
flowchart LR
    R["要件を選定"] --> D["設計を確定"]
    D --> C["設定・manifest作成"]
    C --> V["静的検証"]
    V --> B["構築"]
    B --> A["受入確認"]
    A --> U["As-built・判断記録を更新"]
    U --> N["次のStage"]
```

1. [要件・設計台帳](requirements-and-design.md)から対象項目を選び、採用理由、設定値、依存関係、
   受入条件を確定する。
2. [パラメータ・アドレス割り当て台帳](parameter-and-address-allocation.md)と
   [構成設計と構成図](architecture.md)を更新し、Kubernetes 内外の経路と責務を確認する。
3. [検証ワークロード設計](test-workloads.md)から対象workloadとTest IDを選び、kind設定、Helm values、
   Kubernetes manifest、確認コマンドを作成する。
4. schema、render結果、差分、アドレス重複、秘密情報の有無を静的に検証する。
5. ユーザーが対象と操作を明示した後にlabへ構築する。
6. 疎通だけでなく、状態、経路、可観測性、障害時動作を段階内で受入確認する。
7. 実測値をAs-builtへ反映し、台帳を`Validated`または課題付き`Open`へ更新する。

## 3. 共通の構築記録

各Stageで最低限次を記録する。runtime出力やsystem dumpはGit管理対象外へ保存する。

- 実施日時、担当、lab名、Git commitまたはworktree状態
- kind、Kubernetes、kubectl、Cilium、Cilium CLI、Hubble CLI、Helm、Tetragonのversion
- 要件・設計台帳の対象IDと、確認済み公式URL
- 使用したkind設定、Helm values、manifest
- 構築前後の変更点とrollback方法
- `kubectl get nodes -o wide`、Pod配置、各componentのstatus
- 期待状態、実測状態、判定、残課題
- NX-OS側BGP、route、counterの確認結果
- 失敗時のsystem dump保存先。dumpそのものはcommitしない

## 4. Stage 0: 初期要件・基本設計

### 構築する状態

まだlabへ変更を加えず、Stage 1を安全に作成できる設計baselineを作る。後段の全設定を完全に
決めるのではなく、kind基盤とkube-proxy-free Ciliumに必要な値を確定し、後段の未決事項を明示する。

### 設計・作成項目

- [x] Containerlab `v0.78.2` 内蔵 kind library `v0.31.0` と Kubernetes `v1.35.5` Node image の組み合わせ、digest、`kind load` の制約を確定する
- [x] Cilium `v1.20.1`、Cilium CLI `v0.19.7`、Hubble CLI `v1.19.4`、Helm chart の version を固定する
- [ ] kubectl、Cilium CLI、Hubble CLIをsite別version fileで固定し、共通準備scriptの`--check`を合格させる
- [x] Tetragon `v1.7.0` と chart version の対応を確認する
- [x] host kernel、eBPF config、BTF、cgroup v2 の preflight を作成して実行する
- [x] bpffs、tracefs、host `/proc` mount の設計方針を決める
- [x] k02／k03 の Pod、Service、LoadBalancer CIDR と Node PodCIDR mask を割り当てる
- [x] ADC BGR `65010`、k02 `65012`、BDC 論理 BGR `65020`、k03 `65022` の ASN 台帳と変更境界を確定する
- [x] BDC BGP endpoint pool `172.16.253.0/24`、`fd21:0:0:253::/64` と Leaf 固有 address を予約する
- [x] k03 Node の `172.16.0.0/16` route next-hop と BDC Anycast Gateway が `172.16.5.1` で一致することを実測する
- [x] Node ごとの `eth0`、`eth1`／`eth2`、bond、VLAN、IP、MTU、route を As-designed 表にする
- [x] k02 の local VLAN `14`／`104` が VNI `10104` で `Up` となり、local port-channel／remote `nve1` で MAC 学習することを実測する
- [x] k02 Node-facing trunk は VLAN `1-4094` の許可を維持し、port-channel／member MTU `9216` の公開 config を準備する
- [x] k02 Leaf の対象 port-channel／member MTU `9216` を running-config へ適用し、LACP と trunk all を確認する
- [x] ADC Leaf 4 台の k02 Node-facing MTU／description 修正を startup-config へ保存する
- [x] k02 Node MTU `9100` を適用し、Fabric API の IPv4／IPv6 `/livez` HTTP `200` を確認する
- [ ] Cilium／Pod MTU `9000` の導入後に PMTUD、fragment、path MTU boundary を確認する
- [x] k03 の全 Node が `bond0.105`、Leaf 側が VLAN `105`／VNI `10105` であることを確認する
- [x] API は `eth0`、Node InternalIP は Fabric IP とする役割分担と bootstrap 順序を決める
- [x] 管理 API を primary、control-plane Fabric IP の TCP `6443` を secondary とし、証明書 SAN へ含める
- [ ] 対象network-multitoolの既存VLAN、IPv4/IPv6、gateway、leaf接続portを確認する
- [ ] 対象network-multitoolへのCLI/kubeconfig bind追記案を作成し、container再作成単位を決める
- [ ] Containerlab実行hostのsite別PATH/KUBECONFIG設定とversion確認手順を準備する
- [ ] VIP利用clientを含むfabric側prefixの戻りrouteを確定する
- [x] Egress Gateway の single-site 専用 overlay、worker 2 Node、`bond0.104`、Gateway ごとの Egress IP、外部試験 server を割り当てる
- [x] Stage ごとの設定ファイル配置と rollback 単位を決める
- [ ] `lab-smoke`、`egress-probe`、`starwars`、`clustermesh-demo`のimage、digest、namespace、manifest境界を確定する
- [x] 段階構築と同じ設定部品を使う `singlesite-final`、`multisite-final` profile と適用順序を設計する

### Stage 1 と multisite 展開前に作成済みの設定

2026-08-24 時点で次の設定を静的に作成した。稼働中の k02／k03 には未適用であり、Kind Node の再作成と
Cilium Helm release の作成は後続作業とする。

| 成果物 | single-site | multisite | 状態 |
|---|---|---|---|
| Kind config | `nxos_singlesite/k8s_kind/k02/k02.kind.yaml` | `nxos_multisite/k8s_kind/k02/k02.kind.yaml` | 同一内容。Node image は各 topology の kind 共通値で Kubernetes `v1.35.5` digest 固定 |
| k03 Kind config | 対象外 | `nxos_multisite/k8s_kind/k03/k03.kind.yaml` | k03 固有 Pod／Service CIDR、API SAN、Node PodCIDR mask、mount を設定 |
| Containerlab post-link | `nxos_singlesite/nxos-fabric-singlesite.clab.yaml` | `nxos_multisite/nxos-fabric-multisite.clab.yaml` | bond／VLAN 作成後に k02／k03 の kubelet Node IP を更新 |
| Cilium base values | `nxos_singlesite/k8s_kind/k02/cilium/values/00-base.yaml` | `nxos_multisite/k8s_kind/k02/cilium/values/00-base.yaml` | Helm `v4.2.4`／chart `v1.20.1` で render に合格 |
| Cilium 初期 overlay | observability／single-site Egress | observability／Cluster Mesh | Hubble を初期導入し、site profile ごとの差分を分離 |
| Cilium LB IPAM／BGP resource | k02 pool／worker peer | k02／k03 pool／worker peer | worker 2 Node だけを speaker にする実ファイルを作成済み |
| Cluster Mesh API Service | 対象外 | k02／k03 の外部管理 Service | chart template にない `RequireDualStack` と固定 VIP を実ファイルで指定 |
| Tetragon values | k02 observe-only | k02／k03 observe-only | Cilium Ready 後に同じ初期構築手順で導入する |
| k03 Cilium base values | 対象外 | `nxos_multisite/k8s_kind/k03/cilium/values/00-base.yaml` | cluster ID `3`、k03 Fabric NodePort CIDR を設定し、chart `v1.20.1` で render に合格 |
| Cilium runtime values | `nxos_singlesite/k8s_kind/k02/cilium/runtime/10-k8s-api.yaml` | `nxos_multisite/k8s_kind/k02/cilium/runtime/10-k8s-api.yaml` | クラスタ作成後に生成、Git 管理外 |
| k03 Cilium runtime values | 対象外 | `nxos_multisite/k8s_kind/k03/cilium/runtime/10-k8s-api.yaml` | クラスタ作成後に生成、Git 管理外 |
| CoreDNS runtime parameter | `nxos_singlesite/k8s_kind/k02/cilium/runtime/20-coredns-upstream.env` | k02／k03 の site 別 `cilium/runtime/20-coredns-upstream.env` | Pod から到達確認した resolver を実行時選定し、Git 管理外で記録 |
| 共通スクリプト | `scripts/cilium-lab/configure-kubelet-node-ip.sh` | 同左 | local address 検証、kubelet restart を冪等化 |
| 共通スクリプト | `scripts/cilium-lab/render-k8s-api-values.sh` | 同左 | 全 Node から API `/livez` を確認後に出力 |
| 共通スクリプト | `scripts/cilium-lab/configure-coredns-upstream.sh` | 同左 | resolver 自動検出／明示指定、direct／Cluster DNS test、失敗時 rollback |
| Egress address スクリプト | `scripts/cilium-lab/configure-egress-gateway-addresses.sh` | 実験 profile だけで使用 | Gateway ごとの secondary IPv4／IPv6 を冪等設定する。実ファイル作成済み、running Node へ未適用 |

両 Kind config には `disableDefaultCNI: true`、`kubeProxyMode: none`、dual-stack Pod／Service CIDR、
API Fabric address の certificate SAN、Node PodCIDR mask、Tetragon 用 `/procHost` mount を含めた。
Cilium base values には Kubernetes IPAM、VXLAN、kube-proxy replacement、MTU `9000`、
`devices: "eth0,bond0.+"`、Fabric NodePort CIDR、BGP Control Plane を含める。初期 overlay で Hubble と
site profile を重ね、Cilium Ready 後に LB IPAM／BGP resource と Tetragon を同じ構築手順内で導入する。
試験アプリ、Egress policy、Network Policy、TracingPolicy は初期構築から分離する。

確定した値は [パラメータ・アドレス割り当て台帳](parameter-and-address-allocation.md)を正本とする。
`[x]` は設計値の確定を示し、lab への適用や実測完了を示さない。

### 完了状態

- 使用versionとdigest、アドレス、interface、MTUのbaselineが文書化されている。
- site別CLI cacheがlocal checksumと報告versionの検証に合格している。
- NX-OSを通るnode間経路を構成図で説明できる。
- Stage 1とStage 2の対象項目が`Ready`である。
- 未決事項が後段のどのStageで判断されるか明示されている。

## 5. Stage 1: single-site kind + kube-proxy-free Cilium基盤

### 構築する状態

`nxos_singlesite/adc-k02` を最初から default CNI と kube-proxy なしで作成し、直後に Cilium を
kube-proxy replacement 有効で導入する。初期構築では Hubble、LB IPAM／BGP resource、
Egress Gateway feature gate、observe-only の Tetragon まで導入する。試験アプリと各種 policy は
リソース判定が合格するまで適用しない。

### 設計・作成項目

- kind node imageをdigest固定する
- `disableDefaultCNI: true`、`kubeProxyMode: none`、dual-stack Pod/Service CIDRを明示する
- node role、extra mount、kubeadm patchを明示する
- Tetragonを後付けしてもnodeを再作成せずに済むよう、host `/proc`を`/procHost`へ初回からmountする
- Node `InternalIP`、default route、NX-OS向けrouteの選択方法を設定する
- control-plane `eth0` IPv4 を自動取得して全 Node から到達確認し、`k8sServiceHost` と
  `k8sServicePort: 6443` へ渡す
- API server証明書SANへFabric側IPv4/IPv6を追加し、管理endpointとFabric endpointを同時に維持する
- kubeletのdual-stack `node-ip`を各nodeの`bond0.<VLAN>` addressへ固定する
- CiliumはVXLAN、Kubernetes IPAM、`kubeProxyReplacement: true`で導入する
- Cilium／Pod MTU `9000`、Node Fabric interface MTU `9100` を明示する
- Ciliumの`devices`に管理用`eth0`とfabric側`bond0.<VLAN>`を含める
- `nodePort.addresses`をk02のfabric側IPv4/IPv6 CIDRへ限定する
- `bgpControlPlane.enabled: true`と`defaultLBServiceIPAM: none`を初回valuesへ含める
- Cilium Helm values、install／status、rollback 手順を作成する
- worker 2 Node だけへ BGP speaker label を付け、LB IPAM／BGP resource を適用する
- Hubble と observe-only の Tetragon を初期構築し、試験アプリを適用しない状態でリソースを測定する
- リソース判定後に [検証ワークロード設計](test-workloads.md)の `lab-smoke` を使い、dual-stack ClusterIP／NodePort を確認する

### 受入確認

- [ ] kube-proxy Podが存在せず、Cilium agent/operatorと全nodeがReadyになる
- [ ] CoreDNSのA/AAAA名前解決が成功する
- [ ] 通常管理kubectlとCilium agentが`eth0`側primary endpoint経由でAPI serverへ到達する
- [ ] Fabric側network-multitoolでtopology設定済みPATHのkubectlがcontrol-plane Fabric IP:6443経由で同じAPI serverへ到達する
- [ ] primary/secondaryの一方を試験的に遮断しても、もう一方の経路と役割を説明できる
- [ ] Node `InternalIP`が設計値と一致する
- [ ] Ciliumの検出deviceとNodePort addressが設計値と一致する
- [ ] 同一node・異なるnodeのPod間IPv4/IPv6が成功する
- [ ] ClusterIP、NodePort、Podから外部への通信が成功する
- [ ] Cilium connectivity testが既知のkind制約を除いて成功する
- [ ] VXLAN UDP 8472とnode間trafficがNX-OS側pathを通る
- [ ] VLAN 14/104間をVNI 10104経由でARP/NDPとIPv4/IPv6通信が通る
- [ ] Docker管理networkへの意図しない迂回がない
- [ ] `/procHost`、cgroup、bpffs、tracefsが設計どおり見える
- [ ] path MTU boundaryとworker再起動後の復旧を確認できる
- [ ] 同じ設定からクラスタを再作成できる

## 6. Stage 2: 外部接続

外部接続をinboundとoutboundに分ける。Stage 2Aで外部clientからService VIPへのinboundを確立し、
そのAs-built構成を維持したままStage 2BでPodから外部serverへのoutboundを追加する。同じStage内でも
設定、manifest、受入結果、rollbackは別の変更単位として記録する。

### 6.1 Stage 2A: Cilium LB IPAMとBGP Control Plane

#### 構築する状態

Stage 1 の初期構築で適用済みの `CiliumLoadBalancerIPPool` と BGP Control Plane v2 resource を使い、
LoadBalancer VIP の割り当てと経路広告を試験する。MetalLB は導入しない。初期 advertisement は
LoadBalancer VIP だけとし、Pod CIDR 広告は分離する。

#### 設計・作成項目

- `k02-infra`／`k02-app`、`k03-infra`／`k03-app` の dual-stack LB IPAM pool と、k01 MetalLB pool の非重複
- IPv4／IPv6 を別 session とする BGP peer、ASN、AFI／SAFI、advertisement selector
- ADC は `adc-bgrt0101/0102`、BDC は `bdc-lfsw0101/0102` の専用 loopback で終端する site 別 peer 設計
- BDC Leaf の `local-as 65020 no-prepend replace-as`、eBGP multihop、EVPN Type-5、prefix filter、multipath
- Keepalive `10`、Hold `30`、k03 multihop TTL `5`、`maximum-prefix 64`、`maximum-paths 4`。BFD は無効
- `defaultLBServiceIPAM: none`と`loadBalancerClass: io.cilium/bgp-control-plane`
- IPv4/IPv6を必須にする`ipFamilyPolicy: RequireDualStack`
- 初回から使用する Cilium `/26`／`/112` 集約と、不合格時の直接 BGP 終端／DCI BGW 集約への rollback
- advertisement 前に worker 2 Node へ設定する site aggregate blackhole route と冪等 script
- Cilium 集約時の未割り当て VIP、重複 path attribute、`externalTrafficPolicy: Local`、withdraw、rollback
- worker の normal／planned-shut profile、`bgp-maintenance` 状態遷移、ADC BGR／BDC Leaf の route 退避、復旧順序
- `lab-smoke`の同一backendを使う`externalTrafficPolicy: Cluster/Local`のService分離
- `externalTrafficPolicy`、SNAT/DSR、Maglevの切替方法
- resource削除時のVIP withdrawとrollback手順

#### 受入確認

- [ ] 希望poolからIPv4/IPv6 VIPを1つずつ割り当てる
- [ ] BGP resource 適用前に worker 2 Node の `/26`／`/112` route type が `blackhole` である
- [ ] NX-OS peer との BGP session と初期 Cilium `/26`／`/112` aggregate を確認できる
- [ ] 未割り当て VIP を試験し、Node 内で破棄されて routing loop がないことを判断できる
- [ ] DCI 公開 scope と集約ポイントを比較表の最終選定規則に従って確定できる
- [ ] BGP sessionとVIP trafficの送受信interfaceが`bond0.<VLAN>`である
- [ ] k02 から見える peer ASN が `65010`、k03 から見える peer ASN が `65020` である
- [ ] k03 の peer address が Leaf 固有 loopback であり、Anycast Gateway と peering していない
- [ ] external clientからVIP、node、PodまでをCiliumとNX-OSで追跡できる
- [ ] ECMPと`externalTrafficPolicy: Cluster/Local`の差を説明できる
- [ ] Agent再起動、node停止、全backend消失時の広告変化を確認できる
- [ ] worker を `planned-shut` へ移して session uptime を維持したまま target route を backup にし、`withdrawn` 後も残存 path で VIP traffic が継続する
- [ ] normal／planned-shut profile 切替時の Established 時刻、community、best path、FIB、収束時間を測定し、label-based soft drain の採否を判断できる
- [ ] ADC BGR、BDC Leaf を 1 台ずつ Graceful Shutdown／GIR で計画退避し、残存 path で VIP traffic が継続する
- [ ] BGP path を workload scheduling より先に戻し、baseline と同じ next-hop 数へ復旧できる
- [ ] MetalLBなしでVIP割当、経路広告、外部到達が成立する

### 6.2 Stage 2B: Cilium Egress Gateway

#### 構築する状態

Stage 1 で Egress Gateway feature gate と BPF masquerade を有効化済みの single-site k02 へ、
`CiliumEgressGatewayPolicy` と試験アプリだけを追加する。クラスタ再作成や Cilium の Helm upgrade は
行わない。Cluster Mesh へ展開する共通 values には feature gate を含めず、single-site 専用 overlay として
管理する。

#### 設計・作成項目

- `egressGateway.enabled: true`、`bpf.masquerade: true`、`kubeProxyReplacement: true`
- `identityAllocationMode: crd`を維持し、`ciliumEndpointSlice.enabled: false`を確認する
- 初期構築済み Egress Gateway overlay の status 確認と、policy の apply／delete 手順
- `adc-k02-worker`／`adc-k02-worker2` の `gw-a`／`gw-b` 排他的 profile と、namespace `egress-probe`／Pod label で対象を選ぶ selector
- `172.16.0.0/24`、`fd21:0:0:1::/64` と `adc-t1sv0101` を除外する `destinationCIDRs`／`excludedCIDRs`
- Gateway Node A の `bond0.14` secondary address `172.16.4.31/24`、`fd21:0:0:4::3:1/64` と外部からの戻り経路
- Gateway Node B の `bond0.104` secondary address `172.16.4.32/24`、`fd21:0:0:4::3:2/64` と外部からの戻り経路
- Cilium は Egress IP を Node へ動的に追加しないため、重複確認後に専用 Node script で secondary address を設定する
- IPv4／IPv6 を別々の `CiliumEgressGatewayPolicy` とし、選択中 profile の単一 `egressGateway` と `egressIP` を指定する
- Policy では `egressIP` または `interface` のどちらか一方だけを指定する
- Cilium `devices`が選択したfabric interfaceを含むことを確認する
- 既存`adc-t1sv0102`を第一候補とする外部試験serverのaccess log、packet capture、NX-OS counterで送信元変換と経路を確認する
- [検証ワークロード設計](test-workloads.md)の`egress-probe`を使い、policy未適用、selector対象外、
  selector対象、invalid gateway/egress IPを分離する
- 新規Pod作成直後のpolicy反映遅延と、期待しないsource IPで外へ出る時間の測定
- gateway node再起動、policy再適用、既存connection切断、SNAT port枯渇の確認方法
- `gw-a` → `gw-b` の明示的 Policy 切替と Node hard stop を分け、既存 connection 切断、新規 connection の手動復旧時間を測定する
- IPv4とIPv6を別々に確認し、IPv6 BPF masqueradingはbetaとして結果を分離する

Egress IP は Gateway Node の interface へ Policy 適用前から実在する必要がある。Cilium Agent、LB IPAM、
BGP Control Plane は、この address を Node へ動的に割り当てない。本ラボでは Fabric connected subnet 上の
secondary IP を専用の idempotent Node 設定 script で構成し、使用 IP、重複、ARP／NDP、return route を
確認してから address family 別 Policy を適用する。kubelet `--node-ip` 更新とは責務を分ける。

#### 受入確認

- [ ] Egress policy 適用前後で通常 Pod egress と Stage 2A の LB／BGP に regression がない
- [ ] selector対象Podだけが指定gateway nodeを通り、対象外Podはbaseline経路を維持する
- [ ] 外部試験serverが接続元を指定egress IPv4/IPv6として観測する
- [ ] source nodeとgateway nodeが異なる場合もgateway nodeでSNATされる
- [ ] `ip route get`、`cilium-dbg bpf egress list`、node capture、NX-OS counterが同じ経路を示す
- [ ] 宛先CIDR外および`excludedCIDRs`の通信にはpolicyが適用されない
- [ ] gateway selector不一致または利用不能egress IP時のdropを意図したfail-closedとして確認する
- [ ] 新規Podのpolicy反映遅延と、その間に観測されるsource IPを記録する
- [ ] gateway node停止・復旧・policy再適用時の新規通信と既存connectionの挙動を説明できる
- [ ] policy 削除後に通常 egress へ戻り、LB／BGP が継続する

## 7. Stage 3: Hubble と Network Policy

### 構築する状態

初期 platform 構築済みの Hubble Agent／Relay／UI／dynamic metrics を使用し、基本 policy を
段階的に適用する。この Stage では Hubble component を追加せず、試験アプリと policy を追加する。

### 設計・作成項目

- Hubble Relayの公開範囲、mTLS、CLI接続方法
- `hubble status -P`のAPI port-forward経路と、`--server`によるFabric Relay直接経路を分離する
- Hubble UIは通常ClusterIPとport-forwardで管理し、fabric確認用LoadBalancer Serviceは分離する
- fabric公開時のアクセス元制限、終了後のService削除手順
- baseline 記録後、test namespace だけに default-deny ingress／egress、DNS allow、L3/L4 allow を順に追加する
- [検証ワークロード設計](test-workloads.md)の `starwars` を使う identity／Service Account、DNS／FQDN、HTTP L7 policy
- Clusterwide policy は local namespaced policy 合格後へ延期する
- test 終了時に全 Policy を削除して baseline へ戻す rollback
- UI、metrics、flow exportの採否条件

具体的な適用順、Test ID、判断 command、rollback は
[Network Policy／Tetragon 検証計画](network-policy-and-tetragon-test-plan.md)を正本とする。

### 受入確認

- [ ] Relayが全nodeを認識し、FORWARDED/DROPPEDを取得できる
- [ ] site別runtimeから起動したHubble CLIでlocal checksum、version、Relay接続を確認できる
- [ ] port-forwardしたHubble UIへ`eth0`管理経路から到達できる
- [ ] 一時的なLoadBalancer VIPを使う場合はfabric経路で到達し、確認後に公開を解除できる
- [ ] DNS、HTTP、Service frontend/backendをflowで関連付けられる
- [ ] default-denyと各allow policyが期待どおり動作する
- [ ] policy変更前後のverdictを説明できる
- [ ] L7 proxyとobservability追加による重大な通信・resource影響がない

## 8. Stage 4: Tetragon observe-only

### 構築する状態

初期 platform 構築済みの Tetragon を observe-only のまま使用し、限定的な TracingPolicy と
試験 event を追加する。enforcement は有効化しない。

### 設計・作成項目

- kind nodeの`/procHost` mountと`tetragon.hostProcPath`
- process、file、network、privilege event 用の限定的 TracingPolicy。公式 policy library／例を採用 version で review して使用する
- `starwars`の`xwing`を再利用し、不足するeventだけ非privilegedな`TetragonProbe`で発生させる
- file event は `/tmp/tetragon-lab-write`、network event は test Pod の `tcp_connect`／`tcp_close`、privilege event は lab 専用 Pod の `cap_capable` に限定する
- event保存先、filter、retentionと秘密情報を記録しない運用
- Tetragon削除とCilium通信継続を確認するrollback手順

具体的な適用順、Test ID、判断 command、rollback は
[Network Policy／Tetragon 検証計画](network-policy-and-tetragon-test-plan.md)を正本とする。

### 受入確認

- [ ] Tetragon DaemonSetが全nodeでReadyになる
- [ ] process execをPod、namespace、parent/child情報と関連付けられる
- [ ] 対象を限定したfile、connect/accept、privilege eventを取得できる
- [ ] network eventとHubble flowを時刻・Podで突き合わせられる
- [ ] idle時・負荷時のCPU/RAMとevent dropが許容範囲である
- [ ] Tetragon停止・再起動がCilium通信へ影響しない

## 9. Stage 5: multisite Cluster Mesh

### 構築する状態

single-site で `Validated` になった構成を `nxos_multisite/adc-k02` と `bdc-k03` へ展開し、
Cluster Mesh を追加する。各 cluster の LoadBalancer／BGP は site 単位で独立させる。この Stage では
Egress Gateway を同時に有効化せず、Cluster Mesh 単独の基準状態を先に確立する。

### 設計・作成項目

- cluster name／ID `adc-k02/2`、`bdc-k03/3`、Pod／Service CIDR、Node address の一意性
- 両 cluster の Kubernetes domain `cluster.local`、MCS domain `clusterset.local`、Cluster Mesh domain `mesh.cilium.io`
- DCI 経由の Node reachability、MTU、必要 port
- Cluster Mesh API 用固定 LoadBalancer VIP `.14.10`／`.15.10`、BGP advertisement、証明書
- `defaultGlobalNamespace: false`、`policyDefaultLocalCluster: true`、共有 CA、`authMode: cluster`
- 初期から API 2 replica、worker 間 required anti-affinity、PDB、ClientIP affinity とし、この状態で resource を測定する
- ADC BGR 終端と BDC Leaf 重畳終端の差異、site-local BGP endpoint、DCI export policy
- Global Service と MCS API の採用範囲
- 両 cluster へ同一 name／namespace で配置する `clustermesh-demo` と cluster 識別可能な backend 応答
- cluster 間 policy、Hubble CA、障害分離と復旧手順

### 受入確認

- [ ] k02／k03 が同一 Cilium version と datapath mode で動作する
- [ ] Cluster Mesh control plane と remote identity 同期が正常である
- [ ] Cluster Mesh API が worker 2 Node に分散し、1 Pod／1 BGP path の停止中も API VIP が到達可能である
- [ ] k02 と k03 の Pod 間通信が IPv4／IPv6 で成功する
- [ ] Global Service または MCS API の名前解決と backend 選択が動作する
- [ ] cross-cluster policy と Hubble の cluster 識別が動作する
- [ ] API `2379/TCP` 断、Node 間 VXLAN `8472/UDP` 断、DCI 全断、片 cluster 停止を区別して確認できる
- [ ] partition 中も cluster-local workload が継続し、復旧後に再同期する

## 10. Stage 6: 構築後の互換性・発展試験

Stage 5 までの通常構築を合格させた後、機能ごとに独立 profile を作り、一度に複数の主要機能を
追加しない。

### 10.1 Egress Gateway／Cluster Mesh 同時有効化試験

Cilium `1.20.1` の公式文書は両機能を「not compatible」とするが、Helm chart と Egress Gateway manager は
同時有効化を明示的に拒否していない。これを通常構築の前提にはせず、Stage 5 の As-built を基準に
`experimental-egress-clustermesh` を追加する構築後試験として扱う。

- k02 と k03 に別々の `CiliumEgressGatewayPolicy`、local Gateway Node、Egress IP を構成する
- 各 Policy は同じ cluster の Pod と Gateway だけを選択する
- Egress の `destinationCIDRs` は外部試験 server に限定し、両 cluster の Pod／Service／Node CIDR を
  `excludedCIDRs` に明示する
- local Pod → local Gateway → 外部 server の SNAT を cluster ごとに確認する
- remote Pod や remote Gateway が local Policy に取り込まれないことを BPF map で確認する
- cross-cluster Pod 通信、Global Service／MCS API、remote identity、Hubble の非干渉を確認する
- DCI／Cluster Mesh API の障害と local Egress の障害を分離して確認する
- 実験 overlay と Policy を削除し、Stage 5 の基準状態へ戻せることを確認する

具体的な前提、適用境界、Test ID、証拠、停止条件、rollback は
[Egress Gateway／Cluster Mesh 同時有効化試験](egress-clustermesh-coexistence-test.md)を正本とする。
試験に合格しても、公式サポート状態が変わるまでは `multisite-final` に取り込まない。

### 10.2 その他の発展試験

1. Gateway API + Envoy + Cilium LoadBalancer
2. WireGuard と MTU／throughput 比較
3. native routing + Pod CIDR BGP 広告
4. Host Firewall audit mode
5. Bandwidth Manager／BBR
6. Tetragon enforcement

## 11. 最終状態への一括収束

段階構築で各機能が合格した後は、空の対象クラスタを採用済みの最終状態へ収束させる。
これは`manifest/`を再帰的に一括適用する手順にはしない。CiliumとTetragonはversion固定したHelm release、
LB IPAM、BGP、Egress Gateway、Network Policy、試験workloadは依存順を持つKubernetes resource layerとして扱う。

段階構築と最終収束で設定を複製せず、同じbase、Helm values overlay、resource layerを共有する。
段階構築では1 layerずつ適用して受入確認し、新規クラスタの最終収束では互換性のあるCilium valuesを
初回install用に重ね合わせてから、合格済みresource layerを順に適用する。これにより、最終状態を作るためだけの
不要なHelm upgradeを繰り返さない。

### 11.1 final profile

| Profile | 対象 | 含める主要機能 | 含めない機能 |
|---|---|---|---|
| `singlesite-final` | `nxos_singlesite/adc-k02` | Cilium 基盤、LB IPAM／BGP、Hubble、Egress Gateway feature gate、Tetragon | Cluster Mesh、validation workload／Policy |
| `multisite-final` | `nxos_multisite/adc-k02`、`bdc-k03` | Cilium 基盤、site-local LB IPAM／BGP、Hubble、Cluster Mesh、Tetragon | Egress Gateway、validation workload／Policy |
| `experimental-egress-clustermesh` | Stage 5 合格後の `nxos_multisite/adc-k02`、`bdc-k03` | `multisite-final` に local Egress Gateway を一時追加 | 通常構築、再現用 final profile、自動収束の対象外 |

Cilium `1.20.1` の公式文書は Egress Gateway と Cluster Mesh を「not compatible」としているため、
通常の final profile は境界を分ける。同時指定は Helm chart に拒否されないが、公式サポート対象とは
確認できない。local Pod → local Gateway の同時有効化は `experimental-egress-clustermesh` でのみ試験し、
final profile へ自動的に取り込まない。将来互換性が変わった場合も、採用 Cilium version の公式文書と
実測を再確認してから profile を変更する。

### 11.2 収束処理の責務と順序

共通 driver `scripts/cilium-lab/converge-cilium-lab.sh` は、次の処理を明示的な順序と wait 条件付きで実行する。

1. version、checksum、host前提、kubeconfig、cluster名、CIDR重複を事前確認する。
2. 対象profileのHelm valuesとKustomize layerをrenderし、schemaと差分を確認する。
3. Ciliumを`helm upgrade --install`で導入し、Ciliumと全nodeのReadyを待つ。
4. LB IP pool、BGP peer/config/advertisement、Service、policyを依存順に`kubectl apply -k`で適用する。
5. multisiteでは両clusterの基盤合格後にCluster Meshを接続し、remote cluster同期を待つ。
6. TetragonをHelmで導入し、DaemonSet rolloutとevent取得を確認する。
7. platformのReady後にvalidation profileのworkloadを適用し、profile固有の受入確認を実行する。
8. 使用version、render結果、判定と残存workloadを記録し、不要なvalidation profileを削除する。

driverは中断後も再実行できる収束型とし、Containerlab/kindの作成・再作成、destroy、rollbackは暗黙に
実行しない。外側のlab起動と内側のKubernetes収束を別操作にすることで、破壊的操作の対象を明確にする。
secret、kubeconfig、生成されたCluster Mesh credential、実測logはGit管理対象外とする。

### 11.3 ファイル境界

次の責務分離を維持する。

```text
nxos_fabric/
├── scripts/cilium-lab/              # site共通preflight/converge/verify
├── nxos_singlesite/k8s_kind/k02/
│   ├── cilium/values/               # baseとsingle-site overlay
│   ├── cilium/manifests/            # 順序付きKustomize layer
│   ├── cilium/profiles/             # singlesite-final の構成要素一覧
│   └── tetragon/                    # Helm values
└── nxos_multisite/k8s_kind/
    ├── k02/                         # site固有values/resource
    ├── k03/                         # site固有values/resource
    └── profiles/                    # multisite-final の構成要素一覧
```

既存のk01 MetalLB試験用`manifest/`はprofileの入力に含めない。profile定義は「使用するvalues、
resource layer、対象cluster、順序」を列挙するinventoryとし、独自templating engineは導入しない。
profile は作成済みである。実行前は `helm template` と `kubectl kustomize` の offline render を必須とし、
CRD 導入後は `kubectl diff` または server-side dry-run でも確認する。

```bash
nxos_fabric/scripts/cilium-lab/converge-cilium-lab.sh \
  --profile singlesite-final \
  --output-dir /tmp/singlesite-final-render
```

既定は check-only であり、cluster／Node state を変更しない。対象 cluster への変更を明示した作業でだけ
`--apply` を追加する。driver は試験 application、Network Policy、TracingPolicy、Egress policy を適用しない。

## 12. 構築・受入記録テンプレート

```markdown
### Build ID

- Date:
- Stage / Environment:
- Requirement IDs:
- Versions:
- Design decision:
- Files changed:
- Expected state:
- Actual state:
- Acceptance result: ACCEPTED / REJECTED / BLOCKED
- Rollback result:
- Evidence location:
- As-built updates:
- Follow-up:
- References and checked date:
```
