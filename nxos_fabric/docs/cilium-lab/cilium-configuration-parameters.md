# Cilium 設定パラメータ設計

## 1. 文書の目的と適用範囲

この文書は、`adc-k02` と `bdc-k03` に導入する Cilium `1.20.1` の設計値を管理する。
Cilium chart の全 Helm value を転載するのではなく、このラボで明示的に判断する値を対象とする。
各項目について、意味、選択肢、選定結果、選定理由、構築後の変更可否と変更方法を記録する。
「本ラボでの初期設定」は、このラボの要件、構成、resource 制約を踏まえた選定結果を示す。
既定値は、特記がない限り Cilium chart `1.20.1` の新規 install 時の値である。chart に key がなく、
datapath の既定動作として定義される値は「datapath default」と記載する。

設計 profile は次の 4 種類とする。

| Profile | 対象 | 用途 |
|---|---|---|
| `common` | single-site／multisite 共通 | CNI、kube-proxy replacement、LB IPAM、BGP、Hubble の共通設定 |
| `singlesite-egress` | single-site の `adc-k02` | Egress Gateway を含む outbound 試験 |
| `multisite-clustermesh` | multisite の `adc-k02`／`bdc-k03` | Cluster Mesh。Egress Gateway は含めない |
| `experimental-egress-clustermesh` | Stage 5 合格後の `adc-k02`／`bdc-k03` | 同一クラスタ内 Egress と Cluster Mesh の同時有効化試験。通常構築と final profile には含めない |

本文中の「選定済み」は設計判断が完了したことを示し、稼働中クラスタへの適用済みを意味しない。
選定値は site 別の `00-base.yaml`、`10-observability.yaml`、`20-*.yaml` へ反映済みである。
稼働中クラスタには未適用であり、再作成時に完全な values set を render、diff した後に実施する。

## 2. 設定パラメータ一覧

変更区分は次の意味で使用する。

| 区分 | 意味 |
|---|---|
| `不可` | 稼働中 Cluster Mesh では変更しない。新しい cluster ID／CIDR で再作成する |
| `Kind 再作成` | Kind cluster の再作成と Cilium の再導入が必要 |
| `Helm + Agent` | Helm values を変更し、Cilium Agent Pod を再起動する |
| `Helm + Operator` | Helm values を変更し、Cilium Operator も再起動する |
| `Resource` | Cilium CR／Kubernetes resource の apply で変更する |
| `Runtime` | 対応する ConfigMap／CLI で変更でき、通常は Agent 再起動が不要 |

| ID | 項目 | 主な選択肢 | Cilium `1.20.1` 既定値 | 本ラボでの初期設定 | 後からの変更 |
|---|---|---|---|---|---|
| P-01 | Cluster name／ID | 任意の一意名、ID `1..255` または `1..511` | `default`／`0` | k02 `adc-k02/2`、k03 `bdc-k03/3` | 原則 `不可` |
| P-02 | IP family | IPv4、IPv6、dual-stack | IPv4 有効、IPv6 無効 | 全 profile で dual-stack | `Kind 再作成` |
| P-03 | IPAM mode | `kubernetes`、`cluster-pool`、その他 cloud／delegated mode | `cluster-pool` | 全 profile で `kubernetes` | 原則 `Kind 再作成` |
| P-04 | Identity allocation | `crd`、`kvstore`、migration mode | `crd` | 全 profile で `crd` | 条件付き `Helm + Agent` |
| P-05 | Routing mode | `tunnel`、`native` | `tunnel` | 全 profile で `tunnel` | `Helm + Agent`、経路設計変更 |
| P-06 | Tunnel protocol | `vxlan`、`geneve` | `vxlan` | 全 profile で `vxlan` | `Helm + Agent` |
| P-07 | Direct Node route | 有効、無効 | 無効 | 全 profile で無効 | `Helm + Agent` |
| P-08 | Cilium MTU | 自動検出、明示値 | `0`、自動検出 | 全 profile で `9000` | `Helm + Agent` |
| P-09 | PMTU Discovery | 有効、無効 | 無効、packetization mode `blackhole` | 全 profile で有効／`blackhole` | `Helm + Agent` |
| P-10 | kube-proxy replacement | 有効、無効 | 無効 | 全 profile で初回から有効 | 原則 `Kind 再作成` |
| P-11 | Kubernetes API endpoint | 自動検出、明示 host／port | host／port とも空 | runtime の control-plane `eth0` IPv4／`6443` | `Helm + Agent` |
| P-12 | Datapath device | 自動検出、明示 device／wildcard | 空、route から自動検出 | 全 profile で `eth0,bond0.+` | `Helm + Agent` |
| P-13 | NodePort address | 全 device address、CIDR 制限 | `nil`、device ごとに自動選択 | k02／k03 の site 別 Fabric CIDR に制限 | `Helm + Agent` |
| P-14 | Masquerading | iptables、BPF、無効 | IPv4／IPv6 有効、BPF 無効 | single-site Egress は BPF、multisite は初期 BPF 無効。構築後の同時有効化試験だけ BPF 有効 | `Helm + Agent` |
| P-15 | Service LB mode | `snat`、`dsr`、`hybrid`、annotation | `snat`（datapath default） | 全 profile で `snat` | `Helm + Agent` |
| P-16 | Service LB algorithm | `random`、`maglev`、annotation | `random`、annotation 無効 | global `random`、個別 annotation 有効 | `Helm + Agent`／Service 更新 |
| P-17 | LB acceleration | `disabled`、`native`、`best-effort` | `disabled` | 全 profile で `disabled` | `Helm + Agent` |
| P-18 | LB IPAM default | `lbipam`、`nodeipam`、`none` | `lbipam`、LB IPAM 有効 | 全 profile で `none`、LB IPAM 有効 | `Helm + Operator` |
| P-19 | BGP Control Plane | 有効、無効 | 無効、router ID `default`、status 有効 | 全 profile で有効、router ID／status は既定値 | `Helm + Agent`、設定は `Resource` |
| P-20 | Egress Gateway／CES | Egress 有効・無効、CES 有効・無効 | 両方無効 | single-site Egress は有効、multisite は初期無効。Stage 5 合格後の実験 profile だけ Egress と Cluster Mesh を同時有効化 | `Helm + Agent + Operator` |
| P-21 | Hubble／Relay／UI | 各機能を個別に有効化 | Agent 有効、Relay／UI 無効 | Agent／Relay は全 cluster、UI は k02 | `Helm + Agent` または workload rollout |
| P-22 | Hubble 公開方式 | port-forward、ClusterIP、LoadBalancer | Relay／UI Service は `ClusterIP` | 通常 port-forward、試験時だけ専用 LB Service | `Resource` |
| P-23 | Hubble TLS／CA | Helm 自動 CA、外部 CA、共有 CA | TLS／自動生成有効、method `helm`、365 日 | `cronJob`、365 日。multisite は Cluster Mesh と共通の `cilium-ca` | CA 変更は再発行・rollout |
| P-24 | Hubble metrics／redaction | static、dynamic、無効／redaction 有効・無効 | metrics 無効、dynamic 無効、redaction 無効 | dynamic metrics 有効、synthetic data は redaction 無効 | metrics は `Runtime` |
| P-25 | Envoy／L7 | standalone Envoy、有効・無効 | 新規 install は Envoy／L7 有効 | Envoy／L7 有効、Ingress／Gateway API 無効 | `Helm + Agent` |
| P-26 | Policy enforcement | `default`、`always`、`never` | `default` | 全 profile で `default` | `Helm + Agent` |
| P-27 | Cluster Mesh 上限／namespace | `255`、`511`／global、明示 global | `255`／global、MCS API 無効 | `255`、明示 global、`cacheTTL: 10m`、MCS API 無効 | 上限は `不可`、namespace は `Helm + Resource` |
| P-28 | Operator replicas | `1` 以上 | `2` | resource 制約を優先して全 profile で `1` | Helm workload rollout |
| P-29 | BPF map sizing | 自動比率、固定値／preallocate | ratio `0.0025`、preallocate 無効 | 既定値を明示採用 | `Helm + Agent` |
| P-30 | Helm 変更時の rollout | 自動、有効、手動 | Agent／Operator／Envoy／Relay／UI はすべて無効 | component ごとの自動 rollout を有効 | Helm で変更可能 |
| P-31 | 初期対象外機能 | encryption、Host Firewall、Gateway API、L2 等 | 機能ごとに異なる。詳細表を参照 | 全 profile で無効／Deferred | 機能ごとに再設計 |
| P-32 | Cluster Mesh API／HA | chart 管理／外部管理、SingleStack／dual-stack、1／2 replica | `NodePort`、chart 管理、SingleStack、1 replica | 外部管理 dual-stack Cilium LoadBalancer。初期から 2 replica／PDB／worker 分散／ClientIP | `Helm + Resource` |
| P-33 | BGP Service prefix aggregation | exact route、Cilium 集約、直接 BGP 終端集約、DCI BGW 集約 | aggregation length 未指定、exact `/32`／`/128` | 初回から Cilium `/26`／`/112`。speaker Node の blackhole route を advertisement 前に必須化 | `Resource`、Node route、upstream route 変更 |
| P-34 | BGP maintenance／Graceful Restart | `planned-shut` community、selector 除外、Graceful Restart、Hold Timer | maintenance label／profile なし。Graceful Restart 無効、有効時の RestartTime `120` 秒 | normal／planned-shut の 2 profile と `bgp-maintenance` 状態遷移。Graceful Restart は初期無効 | `Resource` |
| P-35 | CoreDNS upstream | Node `/etc/resolv.conf`、明示 resolver IPv4 | CoreDNS `forward . /etc/resolv.conf` | Pod 到達性を事前確認した host resolver を runtime 選定 | `Runtime` |

resource requests／limits は single-site の実測後に確定する。初回 values では limit を設けず、
[リソース設計と preflight](resource-and-preflight.md)の合否基準で測定する。

## 3. Values の管理と共通変更手順

### 3.1 Values layer

最終的には次のように責務を分ける。後に指定した file が前の値を上書きする。

```text
cilium/values/00-base.yaml
cilium/values/10-observability.yaml
cilium/values/20-singlesite-egress.yaml
cilium/values/20-multisite-clustermesh.yaml
cilium/values/30-experimental-egress-clustermesh.yaml
cilium/runtime/10-k8s-api.yaml
```

- `00-base.yaml`: cluster、CNI、datapath、LB IPAM、BGP の共通値
- `10-observability.yaml`: Hubble、Relay、UI、metrics、rollout の値
- `20-singlesite-egress.yaml`: Egress Gateway と BPF masquerading
- `20-multisite-clustermesh.yaml`: Cluster Mesh profile。Egress Gateway を有効にしない
- `30-experimental-egress-clustermesh.yaml`: Stage 5 合格後の同時有効化試験専用。通常構築と final profile では指定しない
- `10-k8s-api.yaml`: cluster 作成後に取得した API endpoint。Git 管理しない

`helm upgrade --reuse-values` は過去の残存値を見落とすため使用せず、毎回 profile に必要な values file を
同じ順序ですべて指定する。Secret、Hubble CA private key、kubeconfig は Git へ保存しない。

### 3.2 共通の変更手順

以下は概念手順である。実行前に対象 cluster、profile、chart version、values file を明示する。

```bash
export KUBECONFIG="${PWD}/runtime/kubeconfig"

helm template cilium oci://quay.io/cilium/charts/cilium \
  --version 1.20.1 \
  --namespace kube-system \
  -f cilium/values/00-base.yaml \
  -f cilium/values/10-observability.yaml \
  -f cilium/values/20-singlesite-egress.yaml \
  -f cilium/runtime/10-k8s-api.yaml > /tmp/cilium-rendered.yaml

helm upgrade --install cilium oci://quay.io/cilium/charts/cilium \
  --version 1.20.1 \
  --namespace kube-system \
  -f cilium/values/00-base.yaml \
  -f cilium/values/10-observability.yaml \
  -f cilium/values/20-singlesite-egress.yaml \
  -f cilium/runtime/10-k8s-api.yaml

kubectl -n kube-system rollout status daemonset/cilium
kubectl -n kube-system rollout status deployment/cilium-operator
cilium status --wait
```

multisite では `20-singlesite-egress.yaml` を site 別の
`20-multisite-clustermesh.yaml` に置き換える。
変更前後に `helm get values cilium -n kube-system --all`、`helm diff` 相当の差分、
`cilium config view` を保存する。失敗時は原因を確認して values を戻し、完全な values set で再度
`helm upgrade` する。履歴を確認せずに機械的な `helm rollback` は行わない。

## 4. 項目別の設計

### P-01 Cluster name／ID

`cluster.name` は観測・Cluster Mesh 内で cluster を識別し、`cluster.id` は identity の一部になる。
ID は mesh 内で一意にする。`clustermesh.maxConnectedClusters: 255` の場合は `1..255`、`511` の場合は
`1..511` から選択する。

- 選択肢: 既存命名に沿う任意の一意名、上限に応じた一意 ID
- Cilium `1.20.1` 既定値: `cluster.name: default`／`cluster.id: 0`
- 本ラボでの初期設定: k02 は `cluster.name: adc-k02`／`cluster.id: 2`、k03 は
  `cluster.name: bdc-k03`／`cluster.id: 3`
- 理由: Containerlab Node 名と site を対応させ、既存の k01 と混同しないため
- 後からの変更: 技術上は変更できるが、既存 workload identity と Cluster Mesh の整合性へ影響する。
  稼働中 mesh では変更せず、新しい cluster として再作成する

### P-02 IP family

- 選択肢: IPv4 only、IPv6 only、dual-stack
- Cilium `1.20.1` 既定値: `ipv4.enabled: true`、`ipv6.enabled: false`
- 本ラボでの初期設定: `ipv4.enabled: true`、`ipv6.enabled: true`
- 理由: Node、Pod、Service、LB VIP、BGP を IPv4／IPv6 で個別に検証するため
- 後からの変更: Cluster／Service／Pod CIDR と kubeadm 設定にも関係するため、Kind cluster を再作成する。
  Helm value だけを変更しない

### P-03 IPAM mode

- 選択肢: `kubernetes`、Cilium `cluster-pool`、multi-pool、cloud provider mode、delegated plugin
- Cilium `1.20.1` 既定値: `ipam.mode: cluster-pool`
- 本ラボでの初期設定: `ipam.mode: kubernetes`
- 理由: Kind が各 Node の `spec.podCIDRs` を管理し、k02／k03 の non-overlap CIDR を明示できるため
- 後からの変更: 既存 Pod IP と Node CIDR へ影響する。別比較 profile で cluster を再作成する

### P-04 Identity allocation

- 選択肢: `crd`、`kvstore`、公式 migration mode
- Cilium `1.20.1` 既定値: `identityAllocationMode: crd`
- 本ラボでの初期設定: `identityAllocationMode: crd`
- 理由: Kubernetes CRD を使用する標準構成であり、Egress Gateway の前提でもあるため
- 後からの変更: migration mode と公式手順がある場合だけ段階移行する。単純な value 置換は禁止し、
  Helm upgrade、Agent rollout、identity と endpoint の再確認を行う

### P-05 Routing mode

- 選択肢: `tunnel`、`native`
- Cilium `1.20.1` 既定値: `routingMode: tunnel`
- 本ラボでの初期設定: `routingMode: tunnel`
- 理由: 初期構築では Pod CIDR の underlay 広告を不要にし、既存 NX-OS EVPN/VXLAN 上で Cilium VXLAN を
  独立して確認できるため
- 後からの変更: 可能。ただし native routing CIDR、NX-OS の戻り経路、masquerading、MTU を再設計し、
  別 profile の Helm upgrade と全 Agent rollout を行う。比較試験では cluster 再作成を推奨する

### P-06 Tunnel protocol

- 選択肢: `vxlan`、`geneve`
- Cilium `1.20.1` 既定値: `tunnelProtocol: vxlan`
- 本ラボでの初期設定: `tunnelProtocol: vxlan`
- 理由: UDP `8472` と 50 byte overhead が明確で、既存 fabric との切り分けが容易なため
- 後からの変更: Helm value を変更して全 Agent を rollout できるが、通信断を伴う。UDP port、MTU、
  tunnel endpoint を再検証する。稼働試験中の in-place 比較は行わない

### P-07 Direct Node route

- 選択肢: `autoDirectNodeRoutes: true`、`false`
- Cilium `1.20.1` 既定値: `autoDirectNodeRoutes: false`
- 本ラボでの初期設定: `autoDirectNodeRoutes: false`
- 理由: tunnel mode では不要で、Node routing table へ余分な direct route を追加しないため
- 後からの変更: Helm upgrade と Agent rollout で変更可能。native routing 比較 profile でのみ検討する

### P-08 Cilium MTU

- 選択肢: `MTU: 0` 相当の自動検出、明示値
- Cilium `1.20.1` 既定値: `MTU: 0`。underlay から自動検出する
- 本ラボでの初期設定: `MTU: 9000`
- 理由: Node Fabric interface `9100`、NX-OS `9216` とし、VXLAN overhead を含めて Pod MTU `9000` を
  収容する設計のため
- 後からの変更: Helm upgrade と全 Agent rollout が必要。Cilium interface、Pod veth、VXLAN、
  DF packet、PMTUD を再確認し、既存 Pod は再作成して MTU を揃える

### P-09 PMTU Discovery

- 選択肢: 有効、無効。packetization mode は対応する Cilium version の選択肢を再確認する
- Cilium `1.20.1` 既定値: `pmtuDiscovery.enabled: false`、
  `pmtuDiscovery.packetizationLayerPMTUDMode: blackhole`
- 本ラボでの初期設定: `pmtuDiscovery.enabled: true`、packetization mode は `blackhole`
- 理由: 複数 site と overlay の MTU 不整合を観測し、black-hole を避けるため
- 後からの変更: Helm upgrade と Agent rollout で変更可能。ICMP／ICMPv6 と PMTU cache を確認する

### P-10 kube-proxy replacement

- 選択肢: Cilium replacement 有効、kube-proxy を維持
- Cilium `1.20.1` 既定値: `kubeProxyReplacement: false`
- 本ラボでの初期設定: Kind は `kubeProxyMode: none`、Cilium は `kubeProxyReplacement: true`
- 理由: eBPF Service LB を最初から使用し、後で kube-proxy を除去するための cluster 再作成を避けるため
- 後からの変更: kube-proxy の有無と bootstrap を跨ぐため、原則 Kind cluster を再作成する。単独で
  Cilium value を無効化しない

### P-11 Kubernetes API endpoint

- 選択肢: Service 経由の自動検出、`k8sServiceHost`／`k8sServicePort` の明示
- Cilium `1.20.1` 既定値: `k8sServiceHost: ""`、`k8sServicePort: ""`
- 本ラボでの初期設定: control-plane `eth0` の runtime IPv4 と `6443` を明示する
- 理由: kube-proxy-free bootstrap を Cilium LoadBalancer VIP や未構築の Fabric 経路へ依存させないため
- 後からの変更: runtime values を再生成し、全 Node から `/livez` を確認して Helm upgrade と Agent
  rollout を行う。固定 VIP へ切り替える場合も API certificate SAN と障害時動作を先に確認する

### P-12 Datapath device

- 選択肢: 自動検出、単一 device、複数 device／wildcard
- Cilium `1.20.1` 既定値: `devices: ""`。non-local route を持つ device を probe する
- 本ラボでの初期設定: `devices: "eth0,bond0.+"`
- 理由: `eth0` の管理/API 経路と、`bond0.<VLAN>` の Fabric／NodePort／BGP／Egress 経路の両方を
  Cilium が扱うため。VLAN ID が site／Leaf で異なっても device wildcard と VNI は独立している
- 後からの変更: Helm upgrade と Agent rollout が必要。誤指定は NodePort、masquerading、Egress を
  停止させ得るため、`ip -br link` と Cilium device 検出結果を先に確認する

### P-13 NodePort address

- 選択肢: 検出した全 native device address、`nodePort.addresses` の CIDR 制限
- Cilium `1.20.1` 既定値: `nodePort.addresses: nil`。device ごとに suitable address を自動選択する
- 本ラボでの初期設定: k02 は `172.16.4.0/24`／`fd21:0:0:4::/64`、k03 は
  `172.16.5.0/24`／`fd21:0:0:5::/64`
- 理由: NodePort を Docker 管理用 `eth0` ではなく Fabric 側だけで公開するため
- 後からの変更: Helm upgrade と Agent rollout で変更可能。listen address、Fabric client からの到達、
  `eth0` で意図せず公開されていないことを確認する

### P-14 Masquerading

- 選択肢: iptables masquerading、`bpf.masquerade: true`、family ごとの masquerading 無効化
- Cilium `1.20.1` 既定値: `enableIPv4Masquerade: true`、`enableIPv6Masquerade: true`、
  `bpf.masquerade: false`
- 本ラボでの初期設定: 共通値は `enableIPv4Masquerade: true`／`enableIPv6Masquerade: true`。
  `singlesite-egress` は `bpf.masquerade: true`、`multisite-clustermesh` は初期状態で `false`。
  `experimental-egress-clustermesh` を重ねる試験中だけ `true`
- 理由: Egress Gateway は BPF masquerading を必要とする。Cluster Mesh の初期構築と基本受入では変更要因を
  分離し、Stage 5 合格後の同時有効化試験でだけ追加するため
- 後からの変更: Helm upgrade と Agent rollout が必要。変更後は native routing CIDR、送信元 IP、
  IPv4／IPv6、NAT map 使用量を再確認する

### P-15 Service LB forwarding mode

- 選択肢: `snat`、`dsr`、`hybrid`、Service annotation による選択
- Cilium `1.20.1` 既定値: kube-proxy replacement datapath は `snat`、
  `bpf.lbModeAnnotation: false`
- 本ラボでの初期設定: global は `loadBalancer.mode: snat`、`bpf.lbModeAnnotation: false`
- 理由: 現在の VXLAN mode では DSR dispatch の選択に制約があり、初期受入を対称な戻り経路で行うため
- 後からの変更: Helm upgrade と Agent rollout で可能だが、DSR は routing mode、dispatch method、MTU、
  source preservation を再設計する。別 profile で比較する

### P-16 Service LB algorithm

- 選択肢: `random`、`maglev`、Service annotation による個別指定
- Cilium `1.20.1` 既定値: `loadBalancer.algorithm: random`、`bpf.lbAlgorithmAnnotation: false`
- 本ラボでの初期設定: global は `loadBalancer.algorithm: random`、`bpf.lbAlgorithmAnnotation: true`
- 理由: 小規模 lab の初期メモリを抑えながら、固定 VIP の一部だけ Maglev を比較できるため
- 後からの変更: annotation 有効化後は Service の
  `service.cilium.io/lb-algorithm` を更新できる。global algorithm、Maglev table size／seed の変更は
  Helm upgrade と Agent rollout が必要で、既存 flow の再配置と map memory を確認する

### P-17 LB acceleration

- 選択肢: `disabled`、`native`、`best-effort`
- Cilium `1.20.1` 既定値: `loadBalancer.acceleration: disabled`
- 本ラボでの初期設定: `loadBalancer.acceleration: disabled`
- 理由: Kind の virtual Ethernet／bond／VLAN 環境では、まず tc datapath を基準にして XDP driver 差を
  混在させないため
- 後からの変更: 対象 NIC の XDP capability を確認後、Helm upgrade と Agent rollout を行う。
  device ごとの attach 状態と通信を再確認する

### P-18 LB IPAM default

- 選択肢: `lbipam`、`nodeipam`、`none`
- Cilium `1.20.1` 既定値: `defaultLBServiceIPAM: lbipam`、`enableLBIPAM: true`
- 本ラボでの初期設定: `defaultLBServiceIPAM: none`、`enableLBIPAM: true`
- 理由: class 無指定の LoadBalancer Service を意図せず Cilium pool から割り当てず、
  `loadBalancerClass: io.cilium/bgp-control-plane` を明示した Service だけを対象にするため
- 後からの変更: Helm upgrade と Operator rollout が必要。pool 自体は `CiliumLoadBalancerIPPool` の
  apply で追加・変更する。ただし割当済み pool の CIDR 削除・縮小は VIP 再割当を伴うため、原則として
  新 pool 追加、Service 移行、旧 pool 無効化の順で行う

### P-19 BGP Control Plane

- 選択肢: 有効、無効。router ID は Node IPv4 由来の `default` または IP pool
- Cilium `1.20.1` 既定値: `bgpControlPlane.enabled: false`、router ID mode は `default`、
  status report は有効
- 本ラボでの初期設定: `bgpControlPlane.enabled: true`、router ID mode は `default`、status report は有効
- 理由: Cilium install 後に BGP resource だけを追加でき、k02／k03 の dual-stack LB VIP を
  ADC BGR／BDC 論理 BGR へ広告できるため
- 後からの変更: 機能 flag は Helm upgrade と Agent rollout。peer、advertisement、timer、ASN は
  `CiliumBGPClusterConfig` 等の v2 resource を apply して変更する。変更前後に exact route または採用した
  aggregate NLRI を確認する

### P-20 Egress Gateway と CiliumEndpointSlice

- 選択肢: `egressGateway.enabled` と `ciliumEndpointSlice.enabled` を個別に有効化／無効化
- Cilium `1.20.1` 既定値: `egressGateway.enabled: false`、`ciliumEndpointSlice.enabled: false`
- 本ラボでの初期設定: `singlesite-egress` は Egress Gateway 有効、CES 無効。
  `multisite-clustermesh` は Egress Gateway／CES とも無効。Cluster Mesh の基本動作が合格した後に限り、
  `experimental-egress-clustermesh` で Egress Gateway を追加し、CES は無効のまま維持する
- 理由: Egress Gateway は kube-proxy replacement、BPF masquerading、CRD identity を必要とし、
  Cilium `1.20.1` の公式文書では Cluster Mesh および CES と「not compatible」と記載されるため。
  一方、Helm chart と Egress Gateway manager には Cluster Mesh との同時有効化を明示的に拒否する
  validation がない。したがって「機能 flag を同時に有効化できない」とは断定せず、公式サポート上の
  非互換と実装上の動作可能性を分けて扱う

| 判断対象 | Cilium `1.20.1` で確認できた状態 |
|---|---|
| Helm values の同時指定 | validation template に明示的な拒否処理はない |
| Agent の同時起動 | 構成上は試験可能だが、このラボでは未実測 |
| local Pod → 同じ cluster の local Gateway | 実装は cluster ごとの CiliumEndpoint／CiliumNode／Policy を参照するため動作可能性がある。ただし公式サポート例は確認できず、構築後試験で判定する |
| remote cluster の Pod／Gateway を跨ぐ Policy | 公式文書は Gateway と selected Pod が同じ cluster であることを要求するため、試験の期待値を「選択されない」とする |
| 機能全体の公式 support status | 公式文書は Cluster Mesh と「not compatible」と明記するため、併用構成は support 対象外として扱う |

- 後からの変更: Helm upgrade と Agent／Operator rollout が必要。Egress IP は選定 Node の Fabric
  interface に実在させてから `CiliumEgressGatewayPolicy` を apply する。通常の multisite profile では
  有効化しない。Stage 5 合格後に
  [Egress Gateway／Cluster Mesh 同時有効化試験](egress-clustermesh-coexistence-test.md)へ従い、
  `experimental-egress-clustermesh` で local Pod → local Gateway、remote identity 混在、Global Service、
  障害復旧、rollback を明示的に試験する。試験合格だけを理由に通常の final profile へ取り込まない

### P-21 Hubble、Relay、UI

- 選択肢: Hubble Agent、Relay、UI を個別に有効化。UI は各 cluster または代表 cluster のみ
- Cilium `1.20.1` 既定値: `hubble.enabled: true`、`hubble.relay.enabled: false`、
  `hubble.ui.enabled: false`
- 本ラボでの初期設定: Hubble Agent と Relay は k02／k03 で有効。UI は k02 で有効、k03 は初期無効
- 理由: flow 観測と multi-cluster 集約を維持しつつ、メモリが厳しい BDC の重複 UI を避けるため
- 後からの変更: Hubble Agent flag は Helm upgrade と Cilium Agent rollout。Relay／UI は Helm upgrade
  と各 Deployment rollout。k03 UI は resource 使用量を確認してから有効化できる

### P-22 Hubble 公開方式

- 選択肢: Kubernetes API 経由の port-forward、ClusterIP への cluster 内接続、NodePort、LoadBalancer
- Cilium `1.20.1` 既定値: Hubble Relay／UI Service は `ClusterIP`
- 本ラボでの初期設定: 通常操作は `hubble-ui`／`hubble-relay` の port-forward。Fabric 経路試験時だけ専用の
  LoadBalancer Service を作成し、`infra` pool の固定 VIP と明示 LB class を使用する
- 理由: 常時公開面を増やさず、必要な試験では Cilium LB IPAM／BGP 経路も検証できるため
- 後からの変更: Service resource の apply／delete だけで変更可能。Hubble 本体の Helm reinstall は不要。
  LoadBalancer 公開時は認証・到達元制限がない lab endpoint として扱う

### P-23 Hubble TLS／CA

- 選択肢: chart による自動証明書、cert-manager、外部で発行した証明書。cluster ごとの CA または共有 CA
- Cilium `1.20.1` 既定値: Hubble TLS／自動生成は有効、method は `helm`、証明書有効期間は 365 日
- 本ラボでの初期設定: 全 profile で自動生成 method を `cronJob`、有効期間を 365 日とする。
  multisite は k02 で生成した共通 `cilium-ca` を k03 install 前に安全な runtime 手順で共有し、
  private key は Git へ保存しない
- 理由: Cluster Mesh 全体の Hubble Relay が相互の flow を検証できる trust を構成するため
- 後からの変更: 可能だが、CA、server certificate、client certificate の順序付き再発行と Relay／Agent
  rollout が必要。期限、SAN、Secret、接続を確認し、単一 Secret の置換だけで済ませない

### P-24 Hubble metrics／redaction

- 選択肢: metrics 無効、static metrics list、dynamic metrics ConfigMap。L7 redaction 有効／無効
- Cilium `1.20.1` 既定値: static metrics list は `nil`、dynamic metrics は無効、redaction は無効
- 本ラボでの初期設定: `hubble.metrics.dynamic.enabled: true` とし、初期 metrics list は最小構成。
  synthetic workload のため `hubble.redact.enabled: false`
- 理由: Agent rollout なしで必要な metrics と context を試験ごとに調整し、初期 cardinality を抑えるため
- 後からの変更: dynamic metrics ConfigMap の更新は通常 Agent 再起動不要。実データを扱う場合は redaction
  を有効にして Helm upgrade と Agent rollout を行い、HTTP header、URL query、Kafka 等の露出を確認する

### P-25 Envoy／L7

- 選択肢: standalone Envoy DaemonSet、有効／無効。L7 policy、Ingress／Gateway API は個別機能
- Cilium `1.20.1` 既定値: 新規 install では `envoy.enabled: true`、`l7Proxy: true`、
  Ingress／Gateway API は無効
- 本ラボでの初期設定: `envoy.enabled: true`。L7 policy の受入に使用し、Ingress／Gateway API は初期無効
- 理由: Cilium Network Policy の HTTP L7 観測・制御を試験しつつ、North-South proxy 機能を同時に
  持ち込まないため
- 後からの変更: Helm upgrade と Agent／Envoy rollout が必要。L7 policy は CNP resource で追加・削除
  できる。Envoy access log の情報量と resource 使用量を確認する

### P-26 Policy enforcement mode

- 選択肢: `default`、`always`、`never`
- Cilium `1.20.1` 既定値: `policyEnforcementMode: default`
- 本ラボでの初期設定: `policyEnforcementMode: default`
- 理由: policy が選択した endpoint だけ default-deny にし、初期 CNI／DNS 受入前に全 Pod を遮断しないため
- 後からの変更: Helm upgrade と Agent rollout で可能。通常は global mode を変えず、KNP／CNP／CCNP
  resource の段階適用で制御する

### P-27 Cluster Mesh 上限と namespace scope

公式ソース: [Cilium Helm Reference](https://docs.cilium.io/en/stable/helm-values/)、
[Cilium Cluster Mesh Network Policy](https://docs.cilium.io/en/stable/network/clustermesh/policy/)

- 選択肢: `clustermesh.maxConnectedClusters` は `255` または `511`。
  namespace は既定ですべて global、または `defaultGlobalNamespace: false` と annotation による明示 global。
  MCS API は個別に有効化できる
- Cilium `1.20.1` 既定値: `maxConnectedClusters: 255`、
  `clustermesh.defaultGlobalNamespace: true`、MCS API は無効
- 本ラボでの初期設定: `maxConnectedClusters: 255`、`clustermesh.defaultGlobalNamespace: false`、
  `clustermesh.policyDefaultLocalCluster: true`、MCS API は初期無効。`cilium-test` namespace だけに
  `clustermesh.cilium.io/global: "true"` を設定する
- 理由: 2 cluster lab では 511 cluster 用 identity layout が不要である。global 対象を試験 namespace に限定し、
  同名 namespace や selector の指定漏れによって remote endpoint へ意図せず範囲を広げないため
- 後からの変更: `maxConnectedClusters` は稼働 cluster で変更できず、mesh 全 cluster で一致させる。
  変更時は cluster 再作成。namespace scope は annotation、MCS API は Helm upgrade と関連 component の
  rollout／resource apply で変更できる

### P-28 Operator replicas

- 選択肢: `operator.replicas` を `1` 以上
- Cilium `1.20.1` 既定値: `operator.replicas: 2`
- 本ラボでの初期設定: `operator.replicas: 1`
- 理由: lab のメモリ消費を抑えるため。これは control plane の高可用性を検証する値ではない
- 後からの変更: Helm upgrade または Deployment scale で可能。ただし宣言値を Helm に戻すため、恒久変更は
  values を更新する。Operator 停止時の LB IPAM、identity、BGP 関連処理への影響を確認する

### P-29 BPF map sizing

- 選択肢: memory ratio による動的 sizing、map ごとの固定値、map preallocation 有効／無効
- Cilium `1.20.1` 既定値: `bpf.mapDynamicSizeRatio: 0.0025`、`bpf.preallocateMaps: false`
- 本ラボでの初期設定: 既定値を明示して `bpf.mapDynamicSizeRatio: 0.0025`、
  `bpf.preallocateMaps: false`
- 理由: Cilium `1.20.1` の既定を初期基準とし、Kind Node のメモリ不足を避けるため
- 後からの変更: Helm upgrade と Agent rollout が必要。変更前後に map pressure、NAT／CT entries、Node
  memory、drop を比較する。上限を下げる場合は現在使用量を先に確認する

### P-30 Helm 変更時の rollout

- 選択肢: value 変更後に手動 rollout、自動 rollout trigger
- Cilium `1.20.1` 既定値: `rollOutCiliumPods` と各 component の `rollOutPods` はすべて `false`
- 本ラボでの初期設定: `rollOutCiliumPods: true`、`operator.rollOutPods: true`、`envoy.rollOutPods: true`、
  `hubble.relay.rollOutPods: true`、`hubble.ui.rollOutPods: true`
- 理由: ConfigMap／Secret の変更を「Helm は成功したが Pod は旧設定」の状態で残さないため
- 後からの変更: Helm values で変更可能。自動 rollout も通信・観測へ影響するため、毎回 render／diff、
  1 component ずつの status、Cilium connectivity を確認する

### P-31 初期対象外機能

次は有用だが、初期 CNI／LB／Hubble／Cluster Mesh の原因切り分けを難しくするため無効または
`Deferred` とする。

| 機能 | Cilium `1.20.1` 既定値 | 本ラボでの初期設定 | 後で有効化する前の確認事項 |
|---|---|---|---|
| WireGuard／IPsec | `encryption.enabled: false` | 無効 | key 管理、Node 間経路、MTU、Cluster Mesh 暗号化範囲 |
| Host Firewall | `hostFirewall.enabled: false` | 無効 | audit mode、管理 `eth0`、API／SSH／Containerlab 経路の allow |
| Gateway API／Ingress | どちらも無効 | 無効 | CRD、Envoy、LB pool、TLS、North-South policy |
| L2 Announcements | `l2announcements.enabled: false` | 無効 | BGP 広告との重複、L2 failure domain、leader election |
| Node IPAM LB | `nodeIPAM.enabled: false` | 無効 | LB IPAM との Service class 分離、Node address 選択 |
| Bandwidth Manager／BBR | どちらも無効 | 無効 | kernel、qdisc、host network、measurement method |
| Local Redirect Policy | 無効 | 無効 | local endpoint、policy、Socket LB との関係 |
| CiliumEndpointSlice | `ciliumEndpointSlice.enabled: false` | 無効 | Egress Gateway との公式非互換、Operator 負荷、Cluster Mesh 対応 |
| Tetragon enforcement | Cilium chart 対象外 | 無効 | observe-only の event loss／noise、TracingPolicy の安全性 |

いずれも「後から有効化可能」であることと「現在の cluster へ安全に追加可能」であることは同義ではない。
採用時はこの台帳へ profile、選択肢、選定理由、依存関係、rollback、受入条件を追加し、公式文書を
再確認してから values または resource を変更する。

### P-32 Cluster Mesh API Service と可用性

公式ソース: [Cilium Cluster Mesh Setup](https://docs.cilium.io/en/stable/network/clustermesh/setup/)、
[Cilium Helm Reference](https://docs.cilium.io/en/stable/helm-values/)

- 選択肢: chart 管理の `NodePort`／`LoadBalancer`／`ClusterIP`、または
  `clustermesh.apiserver.service.externallyCreated: true` と外部 Service resource の組み合わせ
- Cilium `1.20.1` 既定値: `externallyCreated: false`、`type: NodePort`、`externalTrafficPolicy: Cluster`。
  chart template は `ipFamilyPolicy`／`ipFamilies` を出力しないため、Service は Kubernetes の
  SingleStack 既定動作になる
- 本ラボでの初期設定: multisite では `externallyCreated: true` とし、site 別の
  `resources/30-clustermesh-apiserver-service.yaml` で `type: LoadBalancer`、
  `loadBalancerClass: io.cilium/bgp-control-plane`、`ipFamilyPolicy: RequireDualStack`、
  `ipFamilies: [IPv4, IPv6]`、固定 IPv4／IPv6 VIP を指定する。初期から 2 replica、worker 間 required
  anti-affinity、`bgp-speaker=true` の `nodeSelector`、PDB `minAvailable: 1`、Service
  `sessionAffinity: ClientIP` を使用し、この状態で resource を測定する
- 理由: annotation に IPv4／IPv6 VIP を列挙するだけでは Service 自体の dual-stack 要件を宣言できないため。
  chart と Service の二重管理を避け、dual-stack field を実ファイルとして検証可能にする。各 API replica は
  個別の etcd を持つため、ClientIP affinity で不要な backend 切替と full resync の頻度を抑える
- 後からの変更: chart 管理と外部管理の切替は Helm values と Service ownership を同じ変更で扱う。
  `ipFamilies`、VIP、LB class の変更は Service の再作成が必要になる可能性があるため、DNS、証明書 SAN、
  LB IPAM、BGP advertisement、DCI prefix filter を同時に変更し、exact route または採用 aggregate を
  再確認する。replica、affinity、PDB、nodeSelector は Helm upgrade、session affinity は外部管理 Service の
  apply で後から変更でき、Kind cluster の再作成は不要である

### P-33 BGP Service prefix aggregation

- 選択肢:
  - Cilium 既定の exact `/32`／`/128`: VIP 単位の withdraw と DCI filter が明確だが、Service 数に比例して
    route が増える
  - Cilium 集約: Service 所有者に最も近い地点で route 数を減らせるが、未割り当て VIP と path attribute の
    既知問題、`externalTrafficPolicy: Local` の制限がある
  - 直接 BGP 終端集約: ADC BGR／BDC Leaf で exact route を受信してから要約できるが、site 間で実装が非対称に
    なり、Cilium と NX-OS の二重管理になる
  - DCI BGW 集約: local Fabric の exact route を維持できるが、route 数を減らせるのは DCI 区間だけである
- Cilium `1.20.1` 既定値: `aggregationLengthIPv4`／`aggregationLengthIPv6` は未指定で、Service VIP を
  exact `/32`／`/128` として広告する
- 本ラボでの初期設定: Stage 2A の最初の advertisement から k02
  `172.16.14.0/26`／`fd21:0:0:14:0:0:1:0/112`、k03
  `172.16.15.0/26`／`fd21:0:0:15:0:0:1:0/112` を Cilium から広告する
- 選定理由: Cilium が Service selector、VIP、community、advertisement を一元管理でき、k02 の ADC BGR と
  k03 の BDC Leaf 重畳という termination の差を downstream から隠せるため。ただし、Cilium 公式文書は
  aggregate 内の未割り当て VIP への traffic が routing loop になる既知の問題を記載しているため、worker
  2 Node の aggregate blackhole route を BGP resource 適用前の必須条件にする
- 制約: LoadBalancerIP／ExternalIP で `externalTrafficPolicy: Local` の場合、aggregation length は無視される。
  複数 advertisement が同じ aggregate を異なる path attribute で作る動作も undefined である。現在の
  `20-bgp.yaml` にある重複 selector 自体はサポートされる。hybrid では一般 Service だけを集約し、Cluster
  Mesh API は exact route のままにする。同じ aggregation length を異なる attribute で設定しない
- DCI scope: 1 cluster 1 aggregate だけでは infra／application VIP を区別しない。application VIP を site-local
  とする場合は、local aggregate と Cluster Mesh API exact route を同時に広告する hybrid を試験する。
  hybrid が不合格なら exact route を維持するか、reachability scope ごとに pool を分割する
- 後からの変更: `CiliumBGPAdvertisement` の aggregation field を `kubectl diff`、server-side dry-run、
  `kubectl apply` の順で変更する。通常は Helm upgrade や Agent restart を必要としないが、upstream route が
  直ちに変化するため maintenance と rollback を準備する。変更前後に Cilium advertised RIB、直接 peer、
  EVPN Type 5、DCI route、割り当て済み／未割り当て VIP を確認する
- 詳細な比較、Test ID、最終選定規則:
  [Cilium Service VIP 経路集約の比較設計](bgp-route-aggregation-design.md)

### P-34 BGP maintenance／Graceful Restart

- 選択肢:
  - `planned-shut` community: session と route を残し、target worker を backup path へ変更できる
  - Node selector からの明示的除外: soft drain 後に session と route を withdraw できる
  - Cilium Graceful Restart: Agent 再起動中も peer が route を保持できるが、Node 本体の停止では blackhole を
    長引かせ得る
  - Hold Timer による検出: 非計画停止の fallback であり、計画停止の退避手段にはしない
- Cilium `1.20.1` 既定値: maintenance 専用 label／profile はない。`gracefulRestart.enabled` は `false` であり、
  有効化して `restartTimeSeconds` を省略した場合は `120` 秒である。BGP Advertisement は
  `wellKnown: [planned-shut]` で community `65535:0` を送信できる
- 本ラボでの初期設定: prefix なしの `bgp-speaker=true` を role label とする。`bgp-maintenance` label なしは
  normal、`planned-shut` は soft drain、`withdrawn` は selector 非一致とする。site ごとに normal／planned-shut
  の 2 profile だけを用意し、worker 数に応じて maintenance resource を増やさない。Graceful Restart は無効を
  維持する
- 選定理由: Node 本体の停止前に target route を backup として残したまま他方 worker へ切り替え、確認後に
  明示的に withdraw するため。Node 追加時は speaker label と生成した Node override だけを追加する
- 制約: 2 つの `CiliumBGPClusterConfig` selector は排他的にする。normal／planned-shut 切替で session が
  維持されることは公式に無停止保証されていないため、Established 時刻、uptime、route age、community、best
  path、FIB、traffic を実測する。NX-OS の経路選択点では `graceful-shutdown aware` を有効化する。session reset
  または先行 withdraw が発生した場合は不採用とし、NX-OS neighbor policy による soft drain へ切り替える
- 後からの変更: `CiliumBGPClusterConfig.spec.nodeSelector` と `CiliumBGPPeerConfig.spec.gracefulRestart` を
  `kubectl diff`、server-side dry-run、`kubectl apply` の順で変更できる。変更は BGP session と upstream route に
  直ちに影響するため、残存 peer と VIP traffic を確認しながら worker 1 台ずつ実施する
- 詳細な退避手順、NX-OS 側手順、Test ID:
  [Cilium BGP 経路退避とメンテナンス設計](bgp-maintenance-and-route-drain.md)

### P-35 CoreDNS upstream

- 選択肢:
  - CoreDNS 既定の `forward . /etc/resolv.conf` を維持する
  - Pod から到達可能な resolver IPv4 を `forward . <resolver IPv4>` として明示する
- CoreDNS 既定値: Node から継承した `/etc/resolv.conf` を upstream として使用する
- 本ラボでの初期設定: `--upstream`、`COREDNS_UPSTREAM_DNS`、Containerlab host の
  `/etc/resolv.conf` にある最初の非 loopback nameserver の優先順位で runtime 選定する。実値は site 別の
  `cilium/runtime/20-coredns-upstream.env` に記録し、Git 管理しない
- 選定理由: custom Docker network 上の Kind Node では Node の `/etc/resolv.conf` が Docker 組み込み DNS を
  指すことがある。その resolver が Node process から利用できても、Pod CIDR を送信元とする CoreDNS upstream
  query を受理できるとは限らない。環境固有 IP を公開 manifest へ固定せず、Pod からの direct DNS test に合格した
  resolver だけを採用する
- 適用方法: `configure-coredns-upstream.sh` を check-only で実行後、`--apply` を指定する。スクリプトは direct
  upstream test、ConfigMap patch、CoreDNS rollout、Cluster DNS test を実施し、失敗時は元の Corefile へ戻す
- 後からの変更: `Runtime` で変更可能。新 resolver に対する direct test、CoreDNS rollout、internal／external
  DNS、Cilium FQDN cache を再確認する。Kind cluster または Cilium Helm release の再作成は不要である
- 正式資料: Kubernetes 公式の
  [Customizing DNS Service](https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/) は、CoreDNS
  ConfigMap の `forward` を特定 nameserver へ変更する方法を示している。障害時の確認順は
  [Debugging DNS Resolution](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/) に従う

## 5. 適用前後の確認

少なくとも次を確認する。

```bash
helm get values cilium -n kube-system --all
kubectl -n kube-system get pods -o wide
kubectl -n kube-system get configmap cilium-config -o yaml
cilium status --wait
cilium config view
cilium connectivity test
```

機能別には、Hubble Relay 接続、BGP session／advertised route、LB VIP、Egress source IP、
IPv4／IPv6、Node 再起動、Agent rollout 中の通信を追加する。実行 log と Secret を含む dump は
`operations/` または `logs/` に分離し、Git へ追加しない。

設計根拠の公式 URL と確認日は [参照 URL 台帳](references.md)で管理する。
