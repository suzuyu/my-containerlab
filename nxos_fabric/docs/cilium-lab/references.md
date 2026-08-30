# 参照URL台帳

## 運用ルール

- 各構築段階の設計確定前と構築実施前に、該当する公式URLを再確認する。
- `stable`文書が指すversionを確認し、採用versionと異なる場合は差分を記録する。
- release、image、chart、CLIはversionまたはdigestを固定する。
- blogや第三者記事は補助情報とし、設定判断は原則として公式文書またはrelease noteを根拠にする。
- URL確認時は「確認日」「確認したversion」「判断への影響」を更新する。

## Version baseline

| Component | Candidate | Last checked | Official source | Note |
|---|---|---|---|---|
| Containerlab 内蔵 kind library | `v0.31.0` | 2026-08-24 | [Containerlab v0.78.2 go.mod](https://github.com/srl-labs/containerlab/blob/v0.78.2/go.mod#L55) | Containerlab は外部 kind CLI ではなく内蔵 library でクラスタを作成する |
| kind library baseline | `v0.31.0` | 2026-08-24 | [kind v0.31.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.31.0) | 公式に組み合わせて公開された既定 image は Kubernetes `v1.35.0` である |
| kind Node image publisher | `v0.32.0` | 2026-08-24 | [kind v0.32.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.32.0) | Kubernetes `v1.35.5` image の公式 digest を使用する。新 image に対する `kind load` は kind `v0.32.0` 以降を使用する |
| Kubernetes Node image | `v1.35.5` | 2026-08-29 | [kind v0.32.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.32.0) | Kubernetes `1.35.x` では kubeadm `v1beta4` を使用する。k02／k03 の Kind config は移行済み |
| kubeadm configuration API | `v1beta4` | 2026-08-29 | [kubeadm v1beta4](https://v1-35.docs.kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/) | Kubernetes `1.35` の現行 API。k02／k03 の Kind config を `v1beta4` へ移行済み |
| Kubernetes patch changelog | `v1.35.5` | 2026-08-24 | [Kubernetes 1.35 changelog](https://github.com/kubernetes/kubernetes/blob/master/CHANGELOG/CHANGELOG-1.35.md#v1355) | `v1.35.0` の scheduler regression は `v1.35.1`、StatefulSet `Parallel` regression は `v1.35.4` で修正済みである |
| kubectl | `v1.35.5` | 2026-08-22 | [Install kubectl on Linux](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/) | API serverと同一versionを公式binary/checksumで固定する |
| Helm CLI | `v4.2.4` | 2026-08-24 | [Helm v4.2.4](https://github.com/helm/helm/releases/tag/v4.2.4) | 公式 Linux amd64 archive の SHA256 を確認し、Cilium chart render に使用した |
| Cilium | `v1.20.1` | 2026-08-24 | [Cilium v1.20.1](https://github.com/cilium/cilium/releases/tag/v1.20.1) | 2026-08-18 公開の `1.20` patch release |
| Cilium CLI | `v0.19.7` | 2026-08-22 | [Cilium CLI stable](https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt) | Cilium 1.17以降対応。公式archive/checksumを使用する |
| Hubble CLI | `v1.19.4` | 2026-08-30 | [Hubble CLI releases](https://github.com/cilium/hubble/releases/tag/v1.19.4) | 現行 latest。Relay `1.20.1` への接続では version warning が出るが、healthcheck、3 Node 接続、flow 取得を確認した |
| Tetragon | `v1.7.0` | 2026-08-22 | [Tetragon v1.7.0](https://github.com/cilium/tetragon/releases/tag/v1.7.0) | chart/app version対応を導入前に再確認する |

## External client tooling

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| kubectl version skew | 2026-08-22 | [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/) | API serverと同一minorをbaselineにする |
| Cilium CLI release | 2026-08-22 | [Cilium CLI](https://github.com/cilium/cilium-cli) | release archive、SHA256、Cilium互換性 |
| Cilium CLI image | 2026-08-22 | [Official Cilium images](https://github.com/cilium/cilium/blob/main/Documentation/contributing/development/images.rst) | distroless imageは使用せず、公式release binaryを既存serverへmountする |
| Hubble CLI install | 2026-08-22 | [Setting up Hubble](https://docs.cilium.io/en/stable/gettingstarted/hubble_setup/) | release archive、SHA256、port-forwardとdirect Relay接続 |
| Containerlab bind mounts | 2026-08-22 | [Node binds](https://containerlab.dev/manual/nodes/#binds) | topology相対path、read-only directory mount、再作成時の反映を確認する |
| Containerlab k8s-kind | 2026-08-23 | [Kubernetes in Docker](https://containerlab.dev/manual/kinds/k8s-kind/) | kind が `eth0` を管理し、Containerlab が `ext-container` の `eth1+` を接続する責務境界 |
| Containerlab management IP | 2026-08-23 | [Management Network](https://containerlab.dev/manual/network/) | static management IP と Docker IPAM の衝突回避。kind Node は runtime 取得を使用する |
| network-multitool | 2026-08-22 | [srl-labs network-multitool](https://github.com/srl-labs/network-multitool) | Fabric NIC、route、packet確認とKubernetes CLI実行を同じserverで行う |
| network-multitool base | 2026-08-22 | [Network-MultiTool Dockerfile](https://github.com/wbitt/Network-MultiTool/blob/master/Dockerfile) | Alpine baseと既存network commandを確認し、専用mount先で隠さない |

## Cilium foundation

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| kind configuration | 2026-08-24 | [kind Configuration](https://kind.sigs.k8s.io/docs/user/configuration/) | dual-stack、CIDR、default CNI／kube-proxy 無効化、image digest、extra mount、kubeadm patch |
| kind installation | 2026-08-29 | [Installation Using Kind](https://docs.cilium.io/en/stable/installation/kind/) | default CNI 無効化、CIDR、cgroup v2、private cgroup namespace、connectivity test |
| Kubernetes compatibility | 2026-08-24 | [Cilium Kubernetes Compatibility](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/) | Cilium `1.20` は Kubernetes `1.35` を E2E 試験対象として保証する |
| system requirements | 2026-08-29 | [System Requirements](https://docs.cilium.io/en/stable/operations/system_requirements/) | kernel `5.10`、BPF／BTF／cgroup、VXLAN、health、Hubble port |
| routing | 2026-08-23 | [Routing](https://docs.cilium.io/en/stable/network/concepts/routing/) | VXLAN overhead `50` byte、IPv4 underlay、Cilium MTU `9000` |
| kube-proxy replacement | 2026-08-23 | [Kubernetes Without kube-proxy](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/) | bootstrap API endpoint を Cilium LoadBalancer に依存させない |
| Cilium Helm values | 2026-08-29 | [Helm Reference](https://docs.cilium.io/en/stable/helm-values/) | Cilium `1.20.1` の CNI、LB、BGP、Egress、Hubble、Cluster Mesh、rollout、BPF map の選択肢と既定値 |
| Cilium chart schema | 2026-08-24 | [Cilium v1.20.1 values schema](https://raw.githubusercontent.com/cilium/cilium/v1.20.1/install/kubernetes/cilium/values.schema.json) | site 別 base values の key と型を採用 chart version に対して検証する |
| Cilium chart validation | 2026-08-29 | [Cilium v1.20.1 validate template](https://github.com/cilium/cilium/blob/v1.20.1/install/kubernetes/cilium/templates/validate.yaml) | Egress Gateway と Cluster Mesh の同時指定を拒否する validation がないことと、その他の組み合わせ制約を確認する |
| Cilium Egress Gateway manager | 2026-08-29 | [Cilium v1.20.1 manager.go](https://github.com/cilium/cilium/blob/v1.20.1/pkg/egressgateway/manager.go) | Egress manager が local Kubernetes の Policy、CiliumNode、CiliumEndpoint resource を参照し、Cluster Mesh との同時起動を明示的に拒否していないことを確認する |
| Cilium Egress Gateway policy | 2026-08-29 | [Cilium v1.20.1 policy.go](https://github.com/cilium/cilium/blob/v1.20.1/pkg/egressgateway/policy.go) | endpoint／node selector、local Node での Egress IP 導出、Gateway 選択処理を確認する |
| Cilium Helm installation | 2026-08-29 | [Installation using Helm](https://docs.cilium.io/en/stable/installation/k8s-install-helm/) | OCI chart、version 固定、完全な values set、kube-proxy replacement 用 API endpoint、upgrade 手順 |
| Cilium configuration update | 2026-08-29 | [Configuration](https://docs.cilium.io/en/stable/configuration/) | Helm values、`cilium config`、CiliumNodeConfig、Agent rollout の変更範囲 |
| Cilium IPv6 checksum implementation | 2026-08-30 | [Cilium v1.20.1 `lb.h`](https://github.com/cilium/cilium/blob/v1.20.1/bpf/lib/lb.h) | IPv6 reverse NAT の L4 checksum 更新、`BPF_F_IPV6`、旧 kernel 向け fallback path |
| Cilium IPv6 checksum workaround | 2026-08-30 | [Cilium PR #39279](https://github.com/cilium/cilium/pull/39279) | IPv6 underlay checksum 問題に対する Cilium 側 workaround の経緯 |
| Cilium IPv6 checksum long-term fix | 2026-08-30 | [Cilium PR #39631](https://github.com/cilium/cilium/pull/39631) | `BPF_F_IPV6` を使用する long-term solution と旧 kernel fallback の扱い |
| Linux IPv6 L4 checksum stable fix | 2026-08-30 | [Linux stable patch](https://www.spinics.net/lists/netdev/msg1099852.html) | IPv6 reverse SNAT で不正な `skb->csum` が生じる条件、`BPF_F_IPV6`、stable `6.1` から `6.12` 向け patch |
| Cilium BGP v2 resources | 2026-08-29 | [BGP Control Plane Resources](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/) | Node selector、peer timer、multihop、local address override、Service advertisement、overlap community、ECMP |
| Cluster Mesh setup | 2026-08-29 | [Setting up Cluster Mesh](https://docs.cilium.io/en/stable/network/clustermesh/setup/) | unique name／ID／CIDR、`maxConnectedClusters`、LoadBalancer API、共通 CA、certgen、DNS SAN、status command |
| Cluster Mesh troubleshooting | 2026-08-29 | [Cluster Mesh Troubleshooting](https://docs.cilium.io/en/stable/operations/troubleshooting/#cluster-mesh-troubleshooting) | Agent ごとの remote status、KVStoreMesh status、control plane／dataplane の切り分け |
| Cluster Mesh Service affinity | 2026-08-29 | [Service Affinity](https://docs.cilium.io/en/stable/network/clustermesh/affinity/) | `local` は healthy な local backend を優先し、全 local backend 不在時に remote へ fallback する動作 |
| Cilium metrics | 2026-08-29 | [Cilium Metrics](https://docs.cilium.io/en/stable/observability/metrics/) | remote readiness／failure／cache revocation、KVStoreMesh、etcd metric の受入観測 |
| Kubernetes Kustomize | 2026-08-22 | [Declarative Management using Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/) | base/overlay、render、diff、`apply -k` |
| Kubernetes label | 2026-08-29 | [Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/) | prefix なしの private label、`matchLabels`／`matchExpressions`、normal／planned-shut selector の排他性 |
| Kubernetes node IP | 2026-08-22 | [kubelet `--node-ip`](https://kubernetes.io/docs/reference/command-line-tools-reference/kubelet/) | dual-stack Node InternalIPの明示指定 |
| connectivity test | 2026-08-22 | [Connectivity Test](https://docs.cilium.io/en/stable/operations/troubleshooting/) | 基本疎通とsystem dump |

## Test workloads

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| Kubernetes agnhost | 2026-08-22 | [Agnhost](https://github.com/kubernetes/kubernetes/tree/master/test/images/agnhost) | `netexec`のHTTP/UDP endpoint、hostname応答、採用imageのversion/digest |
| Cilium CLI connectivity test | 2026-08-22 | [cilium connectivity test](https://docs.cilium.io/en/latest/cmdref/cilium_connectivity_test/) | IPv4/IPv6、Hubble flow validation、LoadBalancer、Egress Gateway、multi-cluster用optionと使用image |
| Cilium Star Wars demo | 2026-08-22 | [Getting Started with the Star Wars Demo](https://docs.cilium.io/en/stable/gettingstarted/demo/) | deathstar/tiefighter/xwing、L3/L4 identity policy、HTTP L7 policy |
| Egress Gateway example | 2026-08-30 | [Egress Gateway](https://docs.cilium.io/en/stable/network/egress-gateway/egress-gateway/) | Egress IP の事前設定、単一 `egressGateway`、複数 Node 一致時の辞書順選択、Gateway 変更時の既存 connection 切断を確認 |
| Cluster Mesh Global Services | 2026-08-29 | [Load-balancing and Service Discovery](https://docs.cilium.io/en/stable/network/clustermesh/services/) | global／shared annotation、local／remote backend、remote cache TTL |
| Cluster Mesh MCS API | 2026-08-22 | [Multi-Cluster Services API](https://docs.cilium.io/en/stable/network/clustermesh/mcsapi/) | ServiceExport/Import、`clusterset.local`、service affinity |
| Tetragon execution example | 2026-08-29 | [Execution Monitoring](https://tetragon.io/docs/getting-started/execution/) | `xwing` 内の shell／`curl` から process exec／exit と Pod metadata を確認する。multi-node では対象 workload と同じ Node 上の Tetragon Pod を選択する |

## NX-OS EVPN/VXLAN

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| VLAN to VNI mapping | 2026-08-22 | [Configure VXLAN](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/configuration/vxlan/cisco-nexus-9000-series-nx-os-vxlan-configuration-guide-release-106x/m_configuring_vxlan_93x.html) | local VLANとL2 VNIの対応 |
| Port VLAN mapping | 2026-08-22 | [Configuring Port VLAN Mapping](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/configuration/vxlan/cisco-nexus-9000-series-nx-os-vxlan-configuration-guide-release-105x/m_configuring_port_vlan_mapping_93x.html) | access側VLANとVXLAN segmentの変換概念 |

## Load Balancer and BGP

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| Kubernetes dual-stack Service | 2026-08-22 | [IPv4/IPv6 dual-stack](https://kubernetes.io/docs/concepts/services-networking/dual-stack/) | `PreferDualStack`と`RequireDualStack`、Service IP family |
| LB IPAM | 2026-08-29 | [LoadBalancer IPAM](https://docs.cilium.io/en/stable/network/lb-ipam/) | non-overlap pool、Service selector、requested fixed IP、dual-stack、LB class、default IPAM mode |
| BGP Control Plane | 2026-08-22 | [BGP Control Plane](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane/) | v2 resource、peer、service/Pod CIDR広告 |
| BGP configuration | 2026-08-23 | [BGP Resources](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/) | timer `10/30`、eBGP multihop、BFD 設定がないこと、traffic policy |
| Cilium Service prefix aggregation | 2026-08-29 | [BGP Control Plane Resources](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/) | 既定の exact `/32`／`/128`、`aggregationLengthIPv4`／`aggregationLengthIPv6`、`externalTrafficPolicy: Local` では集約指定が無視されること、未割り当て VIP の routing loop、異なる path attribute の既知問題 |
| Cilium virtual VIP traffic draft | 2026-08-29 | [Cilium PR #37623](https://github.com/cilium/cilium/pull/37623) | merge されず、機能を後続 PR へ分割して close。closed は修正済みを意味しない |
| Cilium wildcard Service drop | 2026-08-29 | [Cilium PR #40684](https://github.com/cilium/cilium/pull/40684) | Cilium `1.19.0` へ収録され、`1.20.1` にも含まれる。存在する Service VIP の未定義 port／protocol は drop するが、Service に未割り当ての aggregate 内 address は対象外 |
| BGP operation／Node maintenance | 2026-08-29 | [BGP Operation Guide](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-operation/) | workload drain、Node selector 除外、upstream withdraw 確認、Agent／Node／link failure、Graceful Restart の trade-off |
| BGP planned-shut／profile selector | 2026-08-29 | [BGP Control Plane Resources](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/) | `planned-shut` community `65535:0`、Advertisement selector、ClusterConfig node selector、Established 時刻／advertised route の確認 |
| BGP profile conflict | 2026-08-29 | [BGP Control Plane Troubleshooting](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-troubleshooting/) | 複数 ClusterConfig の selector 重複による `ConflictingClusterConfig` を normal／planned-shut の排他条件で防止する |
| Kubernetes Node drain | 2026-08-29 | [Safely Drain a Node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/) | PodDisruptionBudget、workload eviction、Node ごとの maintenance gate |
| NX-OS VXLAN service-node BGP | 2026-08-22 | [Configuring Layer 4 - Layer 7 Services](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/configuration/vxlan/cisco-nexus-9000-series-nx-os-vxlan-configuration-guide-release-105x/m_configuring_layer_4-layer_7_network_services_integration.html) | Anycast Gateway と直接 peer せず、tenant VRF の Leaf 固有 loopback と eBGP multihop する設計 |
| NX-OS local AS | 2026-08-22 | [NX-OS Unicast Routing Configuration Guide 10.5(x)](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/unicast-routing-configuration/cisco-nexus-9000-series-nx-os-unicast-routing-configuration-guide.pdf) | `local-as`、`no-prepend`、`replace-as` の仕様と制約 |
| NX-OS IPv4／IPv6 RIB show command | 2026-08-30 | [Nexus 9000 NX-OS `10.5(x)` Show Commands](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/command-reference/show/b_n9k_show_commands_1051/m_i_showcmds.html) | IPv4 は `show ip route`、IPv6 は `show ipv6 route` を使用し、address の後に VRF を指定できる構文を確認 |
| NX-OS IPv4／IPv6 FIB show command | 2026-08-30 | [Nexus 9000 NX-OS `10.5(x)` F Show Commands](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/command-reference/show/b_n9k_show_commands_1051/m_f_showcmds.pdf) | `show forwarding ipv4／ipv6 route` の address／prefix、`detail`、VRF 指定を確認。N9Kv では aggregate prefix 自体を指定して受入確認する |
| Nexus 9000v software data plane／ECMP | 2026-08-30 | [Cisco Nexus 9000v `10.5(x)` Guide](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/configuration/n9000v-9300v-9500v/cisco-nexus-9000v-9300v-9500v-guide-release-105x/m-overview.html) | 特定 ASIC を emulate せず software data plane を使用すること、物理 platform と挙動差があり得ること、ECMP が support 対象であることを確認 |
| NX-OS BGP aggregate／EVPN Type 5 | 2026-08-29 | [Cisco VXLAN BGP EVPN Design and Implementation Guide](https://www.cisco.com/c/en/us/td/docs/dcn/whitepapers/cisco-vxlan-bgp-evpn-design-and-implementation-guide.pdf) | 直接 BGP 終端または BGW での `aggregate-address ... summary-only` を Cilium 集約の fallback として比較する |
| NX-OS BGP Graceful Shutdown | 2026-08-29 | [Cisco Nexus 9000 Series NX-OS Unicast Routing Configuration Guide `10.5(x)`](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/unicast-routing-configuration/cisco-nexus-9000-series-nx-os-unicast-routing-configuration-guide/m-n9k-configuring-advanced-bgp-102x.html) | `graceful-shutdown aware`、global／peer context、`send-community`、route-map precedence、alternate path、activate／shutdown／restore の順序 |
| NX-OS GIR | 2026-08-29 | [Cisco Nexus 9000 Series NX-OS System Management Configuration Guide `10.5(x)`](https://www.cisco.com/c/en/us/td/docs/switches/datacenter/nexus9000/sw/105x/config-guides/sys-mgmt/cisco-nexus-9000-series-nx-os-system-management-configuration-guide-release-105x/m-configuring-gir.html) | Leaf 全体の BGP／IGP／vPC isolate、maintenance／normal profile、snapshot、N9Kv での収束時間 |
| Nexus 9000v BFD | 2026-08-23 | [Cisco Nexus 9000v Guide](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/102x/configuration/n9000v/cisco-nexus-9000v-guide-102x.pdf) | virtual platform では BFD を試験対象にしない |
| Private ASN registry | 2026-08-22 | [IANA Autonomous System Numbers](https://www.iana.org/assignments/as-numbers) | `64512-65534` は Private Use、`65535` は Reserved |
| L2 announcements | 2026-08-22 | [L2 Announcements](https://docs.cilium.io/en/stable/network/l2-announcements/) | BGPを使わない場合の比較対象 |

## Hubble and policy

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| Hubble setup | 2026-08-22 | [Setting up Hubble](https://docs.cilium.io/en/stable/gettingstarted/hubble_setup/) | Relay、TLS、port 4244 |
| Hubble CLI | 2026-08-29 | [Network Observability with Hubble](https://docs.cilium.io/en/stable/observability/hubble/) | Agent、Relay、UI、multi-cluster flow、flow filter、verdict、L7 情報 |
| Hubble buffer／Relay | 2026-08-30 | [Hubble internals](https://docs.cilium.io/en/stable/internals/hubble/) | Hubble server の ring buffer、古い event の上書き、Relay による multi-node flow 集約 |
| Hubble flow filter | 2026-08-30 | [Inspecting Network Flows with the CLI](https://docs.cilium.io/en/stable/observability/hubble/hubble-cli/) | Pod／protocol／verdict filter と Relay 経由の flow 観測方法 |
| Hubble UI | 2026-08-22 | [Service Map & Hubble UI](https://docs.cilium.io/en/stable/observability/hubble/hubble-ui/) | ClusterIP、API経由port-forward、UI公開方法 |
| Hubble metrics | 2026-08-29 | [Hubble Metrics](https://docs.cilium.io/en/stable/observability/metrics/) | static／dynamic metrics、context、cardinality、runtime 更新 |
| network policy | 2026-08-29 | [Network Policy](https://docs.cilium.io/en/stable/security/policy/) | KNP、CNP、CCNP、L3/L4/L7 と test namespace 内 default-deny |
| DNS/FQDN policy | 2026-08-29 | [Layer 7 Policies](https://docs.cilium.io/en/stable/security/policy/layer7/) | DNS proxy、FQDN egress、HTTP method／path |
| host firewall | 2026-08-22 | [Host Policies](https://docs.cilium.io/en/stable/security/policy/host/) | audit-firstと管理経路保護 |

## Cluster Mesh and advanced features

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| Cilium component overview | 2026-08-30 | [Component Overview](https://docs.cilium.io/en/stable/overview/component-overview/) | Cilium Agent、Operator、CLI、Hubble の役割 |
| Cluster Mesh overview／architecture | 2026-08-30 | [Multi-Cluster（Cluster Mesh）](https://docs.cilium.io/en/stable/network/clustermesh/intro/) | Pod 間通信、Service、policy、API Server／etcd／KVStoreMesh の役割 |
| Cluster Mesh setup | 2026-08-30 | [Cluster Mesh Setup](https://docs.cilium.io/en/stable/network/clustermesh/setup/) | cluster ID／name、最大 cluster 数、共有 CA、API 公開、接続、変更制約 |
| Cluster Mesh policy | 2026-08-30 | [Network Policy](https://docs.cilium.io/en/stable/network/clustermesh/policy/) | policy は cluster 間で自動配布されず、remote cluster selector を明示する動作 |
| Global Service | 2026-08-30 | [Global Services](https://docs.cilium.io/en/stable/network/clustermesh/global-services/) | global／shared annotation、cache TTL、障害時動作 |
| Service affinity | 2026-08-30 | [Service Affinity](https://docs.cilium.io/en/stable/network/clustermesh/affinity/) | local／remote backend の優先と fallback |
| MCS API | 2026-08-22 | [Multi-Cluster Services API](https://docs.cilium.io/en/stable/network/clustermesh/mcsapi/) | ServiceExport/ImportとDNS |
| Kubernetes Service DNS | 2026-08-23 | [DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/) | 両 cluster で `cluster.local` を共用し、MCS は `clusterset.local` を使用する |
| Gateway API | 2026-08-22 | [Gateway API](https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/) | Envoy、LB IPAM、HTTP/TLS/gRPC/TCP/UDP |
| WireGuard | 2026-08-22 | [WireGuard Encryption](https://docs.cilium.io/en/stable/security/network/encryption-wireguard/) | 暗号化範囲、port、MTU |
| Egress Gateway | 2026-08-29 | [Egress Gateway](https://docs.cilium.io/en/stable/network/egress-gateway/egress-gateway/) | KPR／BPF masquerade／CRD identity の前提。公式文書は Cluster Mesh／CES を「not compatible」とするが、Cluster Mesh との同時指定を chart が拒否するわけではないため、公式サポート外として区別する |
| Egress Gateway troubleshooting | 2026-08-22 | [Advanced Troubleshooting](https://docs.cilium.io/en/stable/network/egress-gateway/egress-gateway-troubleshooting/) | SNAT connection limitsとNAT map utilization |
| BPF masquerading | 2026-08-22 | [Masquerading](https://docs.cilium.io/en/stable/network/concepts/masquerading/) | 対象device、NodePort依存、IPv4/IPv6の成熟度差 |
| Bandwidth Manager | 2026-08-22 | [Bandwidth Manager](https://docs.cilium.io/en/stable/network/kubernetes/bandwidth-manager/) | EDT、BBR、Pod bandwidth annotation |

## Tetragon

| Topic | Last checked | URL | この計画で確認する事項 |
|---|---|---|---|
| Kubernetes installation | 2026-08-22 | [Deploy on Kubernetes](https://tetragon.io/docs/installation/kubernetes/) | Helm、DaemonSet、BTF注意事項 |
| getting started | 2026-08-22 | [Quick Kubernetes Install](https://tetragon.io/docs/getting-started/install-k8s/) | kind固有mount、Pod状態、event取得 |
| events | 2026-08-22 | [Events](https://tetragon.io/docs/concepts/events/) | process、file、network event model |
| tracing policy | 2026-08-29 | [Tracing Policy](https://tetragon.io/docs/concepts/tracing-policy/) | runtime 追加／削除、hook、in-kernel selector、namespace／binary／argument filter と低水準 policy の注意点 |
| policy enforcement | 2026-08-22 | [Enforcement](https://tetragon.io/docs/concepts/tracing-policy/enforcement/) | observe-only後の安全な評価 |
| metrics | 2026-08-22 | [Metrics](https://tetragon.io/docs/installation/metrics/) | event loss、policy、resource観測 |
| troubleshooting | 2026-08-22 | [Troubleshooting](https://tetragon.io/docs/troubleshooting/) | system dump、BPF、log確認 |

## 確認履歴

| Date | Change | Impact |
|---|---|---|
| 2026-08-17 | Cilium v1.20.0、kind v0.32.0、Kubernetes v1.35.5を候補化 | 初期version案を作成 |
| 2026-08-22 | Cilium latestがv1.20.1であることを再確認 | Cilium候補をv1.20.1へ更新 |
| 2026-08-22 | kube-proxy replacement、LB IPAM、dual-stack Serviceを再確認 | k02を初回からkube-proxy-free Ciliumで構築する方針へ変更 |
| 2026-08-22 | Cilium multi-device、Hubble UI Service、NX-OS VLAN/VNI mappingを確認 | 管理/APIを`eth0`、fabric dataplaneとService公開をbond側に分離 |
| 2026-08-22 | kubectl/Cilium/Hubble CLI配布とContainerlab shared namespace制約を確認 | 当初案としてsite別runtime、共通準備script、sidecar適用方針を整理 |
| 2026-08-23 | LB IPAM、BGP、Egress Gateway、API endpoint、MTU の公式資料を再確認 | dual-stack pool、BGP timer／limit、Egress IP、Cilium MTU を割り当て台帳へ確定 |
| 2026-08-23 | Hubble CLI `v1.19.4` と Cilium `1.20.1` の Hubble 手順を再確認 | CLI を `v1.19.4` に固定し、Stage 3 で Relay との実接続を確認する |
| 2026-08-23 | Kubernetes DNS、Cilium Global Service／MCS API を再確認 | k02／k03 とも `cluster.local`、MCS は `clusterset.local` とする |
| 2026-08-22 | 取得済み3 CLIがstatic Linux binaryであることとnetwork-multitoolのbaseを確認 | sidecar案を取り下げ、対象network-multitoolへのread-only directory bindと試験時PATH追加へ変更 |
| 2026-08-22 | Container側と実行host側のCLI探索pathを整理 | Containerはtopologyのenv.PATH、hostはsite別作業shellのPATHで同じruntime binaryを使用する方針へ変更 |
| 2026-08-22 | Cilium 1.20.1 Egress Gateway の前提、公式の非互換表記、policy 反映遅延を再確認 | Stage 2 を inbound の 2A と single-site outbound の 2B へ分離 |
| 2026-08-22 | Cilium/TetragonのHelm管理とKustomizeのrender/diff/applyを再確認 | manifest一括適用ではなく、段階構築と共通部品を使うfinal profileと順序付き収束を将来要件へ追加 |
| 2026-08-22 | Kubernetes agnhost、Cilium公式demo/connectivity test、Tetragon execution例を確認 | 機能別の検証workload suiteとplatformから分離したvalidation profileを追加 |
| 2026-08-22 | NX-OS 10.5(x) の Anycast Gateway BGP 制約、tenant VRF loopback、local AS と IANA ASN 台帳を確認 | ADC BGR `65010`、BDC Leaf 重畳 `local-as 65020`、k03 `65022` と `172.16.253.0/24` endpoint pool を設計 |
| 2026-08-24 | kind `v0.32.0`、Kubernetes `v1.35.5`、Cilium `v1.20.1` chart schema、Helm `v4.2.4` を再確認 | site 別 Kind config、Cilium base values、post-link Node IP 更新、runtime API values 生成を作成し、Helm render に合格 |
| 2026-08-24 | Containerlab `v0.78.2` の kind library `v0.31.0`、kind `v0.32.0` の Node image 制約、Kubernetes `v1.35.0` から `v1.35.5` の修正を再確認 | `k01`～`k03` の Node image を topology 共通値 `v1.35.5` digest 固定へ統一し、個別 Kind config の重複指定を削除。初期構築では registry pull を使用する |
| 2026-08-24 | k03 の初期 Cilium 設計値を k02 と照合 | k03 Kind config、Cilium base／runtime values 手順、post-link Node IP 更新を追加し、chart `v1.20.1` の render に合格。k02 の旧 MetalLB manifest を削除 |
| 2026-08-29 | Cilium `1.20.1` の configuration、Helm values、LB IPAM、Egress Gateway、Hubble、Cluster Mesh を再確認 | 選択肢、選定値、理由、変更区分と変更方法を Cilium 設定パラメータ設計へ集約 |
| 2026-08-29 | Kubernetes `1.35` の kubeadm configuration API を再確認 | `v1beta4` を選定し、k02／k03 の Kind config と `extraArgs` を現行形式へ移行 |
| 2026-08-29 | Cilium `1.20.1` chart 既定値と Egress Gateway／Cluster Mesh の validation を再確認 | 設定表へ既定値を追加。同時指定は chart に拒否されない一方、公式文書上は非互換のため、実装上の禁止ではなく公式サポート外と記載 |
| 2026-08-29 | Egress Gateway manager／Policy 実装と Cluster Mesh 非互換文を照合 | 通常の multisite 構築では分離し、Stage 5 合格後に local Pod／local Gateway だけを対象とする同時有効化試験を追加 |
| 2026-08-29 | Cilium `1.20.1` の system requirement、BGP v2 CRD schema、Cluster Mesh Helm／TLS 手順を再確認 | host／Kind preflight、worker 2 Node 限定 BGP resource、site 別 LB pool／advertisement、Cluster Mesh DNS／共通 CA／DCI 合否基準を作成 |
| 2026-08-29 | Egress IP ownership、Network Policy、Tetragon TracingPolicy を再確認 | Egress IP は運用者が Node へ事前設定し、dual-stack Policy を address family 別に分割。namespaced policy と observe-only Tetragon の初期試験順を確定 |
| 2026-08-29 | Cilium `1.20.1` の Egress Gateway、既存 BGW の DCI EVPN neighbor、Network Policy／Tetragon 手順を再確認 | 当初は複数 Gateway を想定したが、2026-08-30 の再確認で単一 `egressGateway` profile へ訂正 |
| 2026-08-30 | Cilium `1.20.1` Egress Gateway API と実 manifest を照合 | `gw-a`／`gw-b` の排他的手動切替へ統一し、active-active／自動 failover の記載を削除 |
| 2026-08-29 | Cilium Service prefix aggregation と NX-OS BGP aggregate を再確認 | Cilium 送信元集約を第一候補とし、未割り当て VIP の loop と DCI 公開 scope を含む 3 集約点の比較・合否試験を追加 |
| 2026-08-29 | Cilium PR `#37623` と後続 `#40684`、Cilium `1.20.1` の BGP aggregation 警告を照合 | `#37623` の close は未割り当て VIP loop の解消を意味しないと判断。初回 Cilium 集約と speaker Node blackhole route を初期設計へ採用 |
| 2026-08-29 | Cilium Node shutdown、Graceful Restart、Kubernetes drain、NX-OS Graceful Shutdown を再確認 | worker の drain／maintenance selector、router／Leaf の soft drain／hard withdraw、復旧順序、`MNT-*` 合否基準を設計 |
| 2026-08-29 | Cilium `planned-shut`、ClusterConfig selector、NodeConfig status、NX-OS Graceful Shutdown／GIR を再確認 | Node 数に依存しない normal／planned-shut の 2 profile、3 状態 label、Established 時刻／uptime／community／best path／FIB／traffic の試験手順を設計 |
| 2026-08-30 | Cilium `1.20.1` の Cluster Mesh architecture、component、Global Service、policy、Helm values、metrics を再確認 | 設計節へ公式 source link を追加し、初期 API 2 replica／worker 分散／PDB／ClientIP affinity と実 values／resource を同期 |
| 2026-08-30 | Cilium `1.20.1` の Service prefix aggregation と well-known community を実 resource と再照合 | `planned-shut` が `65535:0` に対応することを確認。`externalTrafficPolicy: Local` の exact route を BGP inbound で許可し、aggregate と longest-prefix で共存させる設計へ候補 config を同期 |
| 2026-08-30 | Nexus 9000v `10.5(4)` の BGP／RIB／EVPN と Forwarding 表を比較 | Aggregate の Forwarding 欠落と BGR exact route の 1 path 表示を `TI-002` として分離し、controlled withdraw を最終判定に追加 |
| 2026-08-30 | Hubble CLI `v1.19.4` と Relay `v1.20.1` の実接続を確認 | healthcheck、3／3 Node、両 backend の flow 取得を確認。live Pod filter を Stage 9 手順へ追加 |
| 2026-08-30 | final profile の chart／Kustomize render を再実行 | `singlesite-final`／`multisite-final` inventory と check-only／明示的 `--apply` の収束 driver を作成し、初期 platform と validation workload の境界を確定 |
