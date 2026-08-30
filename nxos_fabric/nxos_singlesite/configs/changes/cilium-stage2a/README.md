# ADC Stage 2A BGP 変更手順

この directory は、既存の k01 MetalLB 接続を維持しながら ADC BGR の ASN を `65535` から
`65010` へ変更し、k02 Cilium BGP peer を追加する投入用 candidate を保持する。

コマンドは NX-OS `10.5(4)` の現行 config を基にしている。実行 directory は
`nxos_fabric/nxos_singlesite`、Kubernetes context は k01 が `kind-adc-k01`、k02 が
`kind-adc-k02` である。

## 1. 変更単位と停止条件

1 系は `adc-lfsw0101`、`adc-bgrt0101`、k01 の `peer-bgprtr01-*` を一つの変更単位とする。
2 系は `adc-lfsw0102`、`adc-bgrt0102`、k01 の `peer-bgprtr02-*` を一つの変更単位とする。

- 1 系の受入確認が完了するまで 2 系を変更しない。
- `no router bgp 65535` は BGR の BGP process と関連 config を削除する。このため BGR candidate は、
  既存 Leaf／k01 neighbor と新規 k02 neighbor を `router bgp 65010` 配下へ完全に再作成する。
- k01 の一方の BGR session は ASN 切替から MetalLB peer 更新まで一時的に down する。未変更側の BGR
  session と Service route が残っていることを確認してから開始する。
- k02 workload は両系の全 8 transport session が `Established` になるまで適用しない。
- 各 candidate に `copy running-config startup-config` は含めない。両系の受入後に保存する。
- NX-OS parser error が 1 行でも出た場合は後続 candidate を投入せず、その装置の
  `show running-config bgp` と該当 section を保存して中止する。

## 2. 変更前 baseline

### 2.1 Kubernetes

```bash
export CLABNAME=nxos-fabric-singlesite
export K01_KUBECONFIG="$PWD/clab-${CLABNAME}/adc-k01/k8s_kind/k01/kubeconfig-k01"
export K02_KUBECONFIG="$PWD/clab-${CLABNAME}/adc-k02/k8s_kind/k02/kubeconfig-k02"
export K01_CONTEXT=kind-adc-k01
export K02_CONTEXT=kind-adc-k02

test -r "${K01_KUBECONFIG}"
test -r "${K02_KUBECONFIG}"
export KUBECONFIG="${K01_KUBECONFIG}:${K02_KUBECONFIG}"
kubectl config get-contexts

kubectl --context "${K01_CONTEXT}" -n metallb-system get bgppeer \
  -o custom-columns='NAME:.metadata.name,MY_ASN:.spec.myASN,PEER_ASN:.spec.peerASN,PEER:.spec.peerAddress'
cilium bgp peers --context "${K02_CONTEXT}"
```

k01 は BGR 1／2 系が `65535` と接続済み、k02 は `65010` を待って `active` であることを初期状態とする。

### 2.2 NX-OS

4 台で次を保存する。

```text
show clock
show running-config bgp
show bgp vrf tenant1-vpc1 ipv4 unicast summary
show bgp vrf tenant1-vpc1 ipv6 unicast summary
show interface port-channel149 trunk
show vlan id 104
```

BGR では k01 peer と Leaf peer、Leaf では BGR peer が `Established` であることを確認する。

## 3. 1 系の変更

### 3.1 `adc-lfsw0101`

[01-adc-lfsw0101.cfg](01-adc-lfsw0101.cfg)を login 済みの `adc-lfsw0101` CLI へ貼り付ける。

この candidate は VLAN `104` を BGR-facing Port-Channel へ追加し、BGR の remote AS を `65010` に変更する。
また、standard community の送信と Graceful Shutdown aware を有効にする。NX-OS `10.5(4)` の runtime parser は
`advertise l2vpn evpn` を deprecated／no effect と判定したため明示せず、Service route の EVPN Route Type 5 化は
workload 適用後の RIB で受入判定する。

### 3.2 `adc-bgrt0101`

[02-adc-bgrt0101.cfg](02-adc-bgrt0101.cfg)を login 済みの `adc-bgrt0101` CLI へ貼り付ける。

### 3.3 k01 の 1 系 peer ASN

```bash
kubectl --context "${K01_CONTEXT}" -n metallb-system patch bgppeer \
  peer-bgprtr01-ipv4 --type merge -p '{"spec":{"peerASN":65010}}'
kubectl --context "${K01_CONTEXT}" -n metallb-system patch bgppeer \
  peer-bgprtr01-ipv6 --type merge -p '{"spec":{"peerASN":65010}}'
```

### 3.4 1 系の受入確認

```bash
kubectl --context "${K01_CONTEXT}" -n metallb-system get bgppeer \
  peer-bgprtr01-ipv4 peer-bgprtr01-ipv6 \
  -o custom-columns='NAME:.metadata.name,PEER_ASN:.spec.peerASN,PEER:.spec.peerAddress'

export SPEAKER_POD="$(kubectl --context "${K01_CONTEXT}" -n metallb-system get pod \
  -l app=metallb,component=speaker -o jsonpath='{.items[0].metadata.name}')"
kubectl --context "${K01_CONTEXT}" -n metallb-system exec "${SPEAKER_POD}" -c frr -- \
  vtysh -c 'show bgp summary'

cilium bgp peers --context "${K02_CONTEXT}"
```

`adc-bgrt0101` で確認する。

```text
show running-config bgp
show interface Vlan104
show interface port-channel149 trunk
show bgp vrf tenant1-vpc1 ipv4 unicast summary
show bgp vrf tenant1-vpc1 ipv6 unicast summary
show bgp vrf tenant1-vpc1 ipv4 unicast neighbors 172.16.4.21
show bgp vrf tenant1-vpc1 ipv4 unicast neighbors 172.16.4.22
show bgp vrf tenant1-vpc1 ipv6 unicast neighbors fd21:0:0:4::2:1
show bgp vrf tenant1-vpc1 ipv6 unicast neighbors fd21:0:0:4::2:2
```

次をすべて満たした場合だけ 2 系へ進む。

- BGR の local AS が `65010` である。
- BGR–Leaf の IPv4／IPv6 session が `Established` である。
- k01 から BGR 1 系への IPv4／IPv6 session が `Established` である。
- k01 の BGR 2 系 session と既存 Service route が維持されている。
- k02 worker 2 Node から BGR 1 系への IPv4／IPv6、計 4 session が `Established` である。
- BGR 1 系への session だけが成立し、未変更の BGR 2 系が `active` であることを既知状態として説明できる。

## 4. 2 系の変更

### 4.1 `adc-lfsw0102`

[03-adc-lfsw0102.cfg](03-adc-lfsw0102.cfg)を login 済みの `adc-lfsw0102` CLI へ貼り付ける。

### 4.2 `adc-bgrt0102`

[04-adc-bgrt0102.cfg](04-adc-bgrt0102.cfg)を login 済みの `adc-bgrt0102` CLI へ貼り付ける。

### 4.3 k01 の 2 系 peer ASN

```bash
kubectl --context "${K01_CONTEXT}" -n metallb-system patch bgppeer \
  peer-bgprtr02-ipv4 --type merge -p '{"spec":{"peerASN":65010}}'
kubectl --context "${K01_CONTEXT}" -n metallb-system patch bgppeer \
  peer-bgprtr02-ipv6 --type merge -p '{"spec":{"peerASN":65010}}'
```

### 4.4 2 系と全体の受入確認

```bash
kubectl --context "${K01_CONTEXT}" -n metallb-system get bgppeer \
  -o custom-columns='NAME:.metadata.name,MY_ASN:.spec.myASN,PEER_ASN:.spec.peerASN,PEER:.spec.peerAddress'
cilium bgp peers --context "${K02_CONTEXT}"
```

`adc-bgrt0102` では 1 系と同じ BGP summary／neighbor command を実行し、peer address だけを
2 系の値へ読み替える。最終合格条件は次のとおりとする。

- k01 の 4 BGPPeer が `peerASN: 65010` で、BGR 1／2 系の IPv4／IPv6 session が成立する。
- k01 の既存 Service VIP route が両 BGR に残る。
- k02 の 8 transport session がすべて `Established` である。
- BGR 1／2 系が k02 worker 2 Node を動的 neighbor として表示する。
- workload 適用前は k02 の advertised／received prefix が `0` でもよい。
- VLAN `104` が Leaf／BGR 両側の `port-channel149` で forwarding される。channel-group 所属中の
  Ethernet member は VLAN list の直接変更が拒否されるため、runtime 変更は Port-Channel だけに適用する。
- 未解消の parser error、BGP maximum-prefix 超過、unexpected route がない。Port-Channel member の Ethernet へ
  `switchport trunk allowed vlan` を直接適用すると拒否されることは確認済みであり、candidate では
  `port-channel149` だけを変更する。

## 5. source manifest の永続化

single-site の k01 manifest にある 4 個の `peerASN` は、最終状態の `65010` へ更新済みである。
runtime patch の受入前に manifest directory 全体を再適用せず、両系の受入後に永続値として適用する。
この source 更新がない状態では、後続の `kubectl apply -f k8s_kind/k01/manifest/` で `65535` へ戻るためである。

```bash
sed -n '1,120p' k8s_kind/k01/manifest/20-metallb-bgppeer.yaml
kubectl --context "${K01_CONTEXT}" apply \
  -f k8s_kind/k01/manifest/20-metallb-bgppeer.yaml
```

NX-OS の最終 config は `configs/singlesite/cisco_n9kv/` の startup source にも反映済みである。
runtime parser で修正が必要になった場合は、candidate だけでなく対応する startup source も同じ内容へ修正する。

## 6. 保存

全条件に合格してから、変更した 4 台で個別に実行する。

```text
copy running-config startup-config
```

保存後に `show running-config bgp` と BGP summary を再取得する。`copy` 実行前であれば、再起動による復旧が
可能な状態を維持できるが、再起動自体は別の承認対象とする。

## 7. rollback 境界

1 系で失敗した場合は 2 系へ進まず、次を一組で `65535` へ戻す。

- `adc-bgrt0101` BGP process
- `adc-lfsw0101` の BGR remote AS
- k01 の `peer-bgprtr01-ipv4`／`peer-bgprtr01-ipv6`

2 系で失敗した場合も同じ考え方で 2 系だけを戻し、検証済みの 1 系は維持する。BGR process rollback は
`no router bgp 65010` により新 process を削除した後、変更前に保存した `show running-config bgp` を
`router bgp 65535` 配下へ完全に戻す。ASN だけを変更して neighbor を省略してはならない。

## 8. 公式資料

- [Cisco Nexus 9000 NX-OS 10.5(x): Configuring Basic BGP](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/unicast-routing-configuration/cisco-nexus-9000-series-nx-os-unicast-routing-configuration-guide/m-n9k-configuring-basic-bgp-101x.html)
- [Cisco Nexus 9000 NX-OS 10.5(x): Configuring Advanced BGP](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/unicast-routing-configuration/cisco-nexus-9000-series-nx-os-unicast-routing-configuration-guide/m-n9k-configuring-advanced-bgp-102x.html)
- [Cisco Nexus 9000 NX-OS 10.5(x): External VRF Connectivity and Route Leaking](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/configuration/vxlan/cisco-nexus-9000-series-nx-os-vxlan-configuration-guide-release-105x/m_configuring_external_vrf_connectivity_and_route_leaking_93x.html)
- [Cilium BGP Control Plane configuration](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/)
