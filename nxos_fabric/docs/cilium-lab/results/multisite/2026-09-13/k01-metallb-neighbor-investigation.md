# k01 MetalLB：BGP 未確立と ARP／ND 到達性

2026-09-13 19:11〜19:19 JST、clab02 でユーザーが構築中の CDC 除外版を調査した。
NX-OS は `10.6(4)`、k01 は Kubernetes `v1.35.5`、host kernel は `5.14.0-611.49.1.el9_7.x86_64`。

## 結果

調査で行った BGR から Node への ping／ping6 後に ARP／ND が学習され、
19:18:56 の確認で **3 speaker × 2 BGR × 2 address family = 12/12 Established** を確認した。
設定変更、BGP clear、ARP／ND clear、再起動は実施していない。
疎通確認によって近隣キャッシュ・接続状態は変化しており、恒久対策を適用したわけではない。

| Node | 調査開始時に未確立だった対向 | 最終状態 |
|---|---|---|
| `adc-k01-control-plane` | BGR01 IPv4、BGR02 IPv6 | 4/4 Established |
| `adc-k01-worker` | BGR01 IPv4／IPv6 | 4/4 Established |
| `adc-k01-worker2` | なし | 4/4 Established |

BGR01 は `172.16.3.4`／`fd21:0:0:3::4`、BGR02 は `172.16.3.5`／`fd21:0:0:3::5`。
最終確認時の送信 prefix 数は worker の各 peer が `1`、control-plane は `0`。
受信 prefix 数 `0` でも JSON の state は Established。VIP の実通信受入は今回の対象外。

## 確認した事実と判定

- worker の BGR01 向け ARP／ND がともに `INCOMPLETE`。FRR は Fabric IP を送信元に選んでいたが、BGP OPEN の送受信数はともに `0`。
- BGR01 の VLAN103 は Up／Up。Node subnet の connected route と AS `65011` の dynamic neighbor 設定があり、worker2 とは両 address family で確立していた。
- BGR01／02 の Po149 は両 member が LACP に参加。worker の bond0 も両 NIC が同じ aggregator に参加し、partner port state はともに `63`。
- Leaf0101／0102 の vPC peer adjacency、設定・VLAN consistency は成功。virtual peer-link、VLAN103／VNI10103、NVE peer は Up。Spine 向け Eth1/7／8 は `port-type fabric` を設定済み。
- BGR01 は Leaf0101、BGR02 は Leaf0102 の Po149 に接続する orphan 構成。各 BGR の MAC は対向 Leaf でも NVE 経由で学習されていた。
- control-plane の TCP/179 接続確認では、`172.16.3.11` から `.4` を求める ARP Request を Leaf0102 の Eth1/4 で 6 回観測した。同時観測した BGR01 の Eth1/49・50 では、その Request は観測されなかった。capture の kernel drop は `0`。
- 同じ BGR01 側の capture では、正常な worker2（`.22`）との ARP Request／Reply は観測できた。control-plane の TCP 接続確認は `No route to host` で終了した。
- BGR01 → worker の IPv4／IPv6、BGR01 → control-plane の IPv4、BGR02 → control-plane の IPv6 の ping 後、対象の近隣キャッシュと BGP が順次成立した。初回 ping は各 3 回中 2 回成功し、worker への後続 IPv4 ping は 3/3 成功した。

以上から、**Leaf を跨ぐ初回 ARP／ND 解決の経路**を優先して調べる。
ARP Request が届かない区間を絞れたが、Leaf 内の破棄箇所、Fabric の BUM 転送、NX-OS の制約／不具合のいずれかは未確定。
ND の未解決と復旧は確認したが、ND packet の同時 capture は行っていない。

Cisco の vPC Fabric Peering ガイドでも、orphan 接続の ARP 動作は physical peer-link と異なると説明されている。
この記載だけで本事象を仕様または特定の不具合と断定しない。
[Cisco 10.6(x) vPC Fabric Peering](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/configuration/vxlan/cisco-nexus-9000-series-nx-os-vxlan-configuration-guide-release-106x/m_configuring_vpc_fabric_peering_93x.html)

## 次の確認と証跡

1. 近隣情報の再学習時にも再現するか確認する。強制的な cache clear は別の試験操作として扱う。
2. 再現時は Node 側、両 Leaf の Fabric uplink、BGR 側を同時 capture し、VNI10103 の BUM 転送と応答経路を照合する。
3. 再現条件を固定した後に設定・イメージの比較試験を検討する。10.6(4)M 固有の障害や、CDC 除外による影響とは現段階で断定しない。

補足：Leaf0102 の `show vpc virtual-peerlink vlan consistency` は `No module named 'tahoe'` で失敗した。
`show vpc brief` による consistency は成功。この診断コマンドの失敗を BGP 未確立の直接原因とは判定していない。

最終状態の FRR JSON は Git 管理外の次の場所に保存した。

`nxos_fabric/nxos_multisite/operations/cilium-lab/2026-09-13/k01-metallb-neighbor-investigation/bgp-191856.json`

初期状態・NX-OS show・短時間 capture は調査時のツール出力に基づく上記の要約であり、pcap ファイルは保存していない。
