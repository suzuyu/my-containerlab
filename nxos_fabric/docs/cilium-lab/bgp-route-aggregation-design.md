# Cilium Service VIP 経路集約の比較設計

## 1. 目的と現在の判断

この文書は、k02／k03 の Cilium Service VIP をどの地点で集約するかを比較し、試験結果から最終採用箇所を
決めるための設計台帳である。稼働中の Cilium resource、NX-OS、Containerlab topology はこの文書更新では
変更しない。

現在の判断は次のとおりとする。

- Cilium BGP Control Plane での送信元集約を初期広告方式として採用する
- 初回から k02／k03 の `/26`／`/112` を広告し、exact route からの切替手順は使用しない
- BGP resource 適用前に BGP speaker Node へ aggregate の blackhole route を設定し、未割り当て VIP を
  Node 内で破棄する
- 公式に記載された未割り当て VIP の routing loop は初期受入試験の必須項目とする
- Cilium 集約が不合格の場合は、ADC BGR／BDC Leaf の直接 BGP 終端で集約する
- DCI BGW は集約の第一候補にせず、site 間公開範囲の最終 filter を担当させる

したがって、設計 status は `Ready` とする。構築後に blackhole route、割り当て済み VIP、未割り当て VIP、
withdraw、rollback が合格した時点で `Validated` とする。

Egress IP はこの Service 集約の対象にしない。k02 の `172.16.24.0/24` と k03 の `172.16.25.0/24`、
対応する IPv6 専用範囲から `/32`／`/128` を割り当て、所有 Node から個別広報する。
[Egress の経路設計](egress-gateway-routed-design.md)に従い、LB 集約の blackhole route と分離する。

## 2. 前提と候補プレフィックス

Cilium BGP Control Plane は、既定では Service VIP を exact `/32`／`/128` で広告する。
`CiliumBGPAdvertisement.spec.advertisements[].service` の `aggregationLengthIPv4` と
`aggregationLengthIPv6` を指定すると Service VIP を集約できる。

現在の LB IPAM range を 1 cluster 1 prefix として表す候補は次のとおりである。

| Cluster | Address family | Cilium 初期集約 | 現在の LB IPAM range | 集約内の未割り当て範囲 |
|---|---|---|---|---|
| k02 | IPv4 | `172.16.14.0/26` | `172.16.14.10-172.16.14.50` | `.0-.9`、`.51-.63` |
| k02 | IPv6 | `fd21:0:0:14:0:0:1:0/112` | 同じ `/112` 内の infra／app pool | Service に未割り当ての予約 address |
| k03 | IPv4 | `172.16.15.0/26` | `172.16.15.10-172.16.15.50` | `.0-.9`、`.51-.63` |
| k03 | IPv6 | `fd21:0:0:15:0:0:1:0/112` | 同じ `/112` 内の infra／app pool | Service に未割り当ての予約 address |

IPv6 pool は `/112` 全体を pool として使用するが、すべての address が常時 Service に割り当てられるわけでは
ない。したがって IPv4／IPv6 とも、Cilium 公式文書の「Service に未割り当ての VIP range へ送信すると
routing loop になる既知の問題」の対象になり得る。

### 2.1 `#37623` と Cilium `1.20.1` の整理

| 対象 | Upstream の状態 | Cilium `1.20.1` での判断 |
|---|---|---|
| PR `#37623` | merge されず `Closed`。機能を後続 PR へ分割 | この PR が直接取り込まれたわけではない |
| PR `#40684` | `main` へ merge され、Cilium `1.19.0` へ収録 | `1.20.1` にも含まれる |
| 存在する Service VIP の未定義 port／protocol | VIP ごとの wildcard Service entry で drop | `#40684` の対象 |
| aggregate 内で Service に未割り当ての IP | Service entry 自体が存在しない | `#40684` の対象外で、公式 BGP 文書の loop 警告が残る |

`#40684` は、最初の対象 frontend が作成された時に VIP ごとの wildcard entry を追加し、最後の frontend が
削除された時に entry を削除する。したがって、これは「存在する VIP の未定義 L4 traffic」を破棄する修正であり、
Service に一度も割り当てられていない aggregate 内 address には entry を作らない。後者の loop 懸念が
Cilium `1.20.1` でも残るという判断は、公式 BGP 文書の警告と `#40684` の実装範囲を照合した推論である。

## 3. 集約ポイントの比較

| 比較項目 | A. Cilium | B. 直接 BGP 終端 | C. DCI BGW |
|---|---|---|---|
| 設定点 | site 別 `CiliumBGPAdvertisement` | ADC BGR／BDC Leaf の tenant VRF BGP | ADC／BDC BGW の EVPN BGP |
| Service 選択との近さ | 最も近い | Cilium から受信した NLRI に依存 | EVPN へ変換後の route に依存 |
| local Fabric で見える route | 集約 prefix | exact route または集約 prefix を選択可能 | exact route のまま |
| DCI で見える route | local policy 次第で集約 prefix | local policy 次第で集約 prefix | 集約 prefix |
| k02／k03 の実装対称性 | 高い | k02 は ADC BGR、k03 は BDC Leaf で非対称 | 高い |
| route 数削減の範囲 | Cilium peer 以降の全区間 | BGP termination 以降 | DCI 区間だけ |
| Service label／community | Cilium resource で一元化しやすい | route-map／attribute-map が必要 | EVPN community と prefix の policy が必要 |
| 個別 VIP の可視性 | upstream では失われる | termination までは保持できる | local Fabric では保持できる |
| 未割り当て VIP | Cilium の既知問題があるため、speaker Node の blackhole route を必須にする | aggregate discard／Null route を設計しやすい | local Fabric では exact route のため影響を限定しやすい |
| `externalTrafficPolicy: Local` | Service VIP の集約指定は無視される | exact route を受けて集約可能だが endpoint 有無との整合試験が必要 | local route を受けて集約可能だが障害時の粒度が粗くなる |
| DCI 公開範囲の分離 | 単一 aggregate では分離不可。aggregate と exact route の hybrid は試験可能 | prefix／community で分離可能 | 最終 export／import filter に適する |
| 変更時の影響 | Cilium resource 更新で route が即時変動 | NX-OS BGP policy 変更 | DCI 全体の EVPN route に影響し得る |
| rollback | aggregation field を外して exact route へ戻す | `aggregate-address`／policy を外す | DCI neighbor policy を外す |

### 3.1 A. Cilium を初期採用する理由

Cilium は Service の選択、VIP、BGP advertisement を同じ Kubernetes resource model で管理できる。
cluster ごとの VIP range を cluster 自身が広告するため、`Cilium → BGP router → Fabric → DCI` の最初の地点で
route 数を減らせ、k02 と k03 の BGP 終端方式の違いも downstream へ持ち込まない。この責務分離は本ラボの
意図に最も合う。

一方、Cilium datapath が所有していない address も aggregate に含まれる。公式文書は、この未割り当て範囲への
traffic が routing loop になる既知の問題を明記している。このため、設定のわかりやすさだけで A を確定せず、
speaker Node に blackhole route を事前設定し、未割り当て address の negative test を必須にする。

### 3.2 speaker Node の安全用 blackhole route

初期 BGP advertisement resource を apply する前に、worker 2 Node へ site 固有 aggregate の blackhole route を
設定する。k02 の概念 command は次のとおりであり、k03 は `.15.0/26` と site `15` の `/112` に置き換える。

```bash
ip route replace blackhole 172.16.14.0/26 metric 42760
ip -6 route replace blackhole fd21:0:0:14:0:0:1:0/112 metric 42760
```

割り当て済み Service VIP は Fabric interface ingress の Cilium eBPF Service datapath で処理される。Service として
処理されず host routing へ渡った packet は blackhole route で破棄する。blackhole route が割り当て済み VIP の
処理を妨げないことは実測が必要であり、不合格なら Cilium 集約を停止する。

この route は Kind Node 再作成で消えるため、site 別 prefix、Node 名、重複、route type を確認する
`configure-bgp-aggregate-blackhole.sh` を作成済みである。Node network 構築後かつ BGP resource 適用前に
worker 2 Node だけへ実行する。

### 3.3 B. 直接 BGP 終端を fallback にする理由

ADC BGR／BDC Leaf は Cilium から exact route を受信できるため、存在する Service route を確認してから
`aggregate-address ... summary-only` などで外向きに要約できる。aggregate に対応する discard route と
more-specific route を同じ routing domain で扱えるため、Cilium Node へ未割り当て VIP が再帰する loop を
避けやすい。

欠点は、k02 と k03 で設定対象が異なること、Cilium resource と NX-OS policy の両方を変更管理すること、
termination より手前の Cilium peer 区間では route 数を削減できないことである。

### 3.4 C. DCI BGW の役割

DCI BGW 集約は DCI 区間だけを簡略化できるが、local Fabric の route 数は減らない。また、DCI neighbor policy
の誤りは Cilium 以外の EVPN route にも影響し得る。このため、BGW は集約の第一候補ではなく、source site の
export と remote site の import を検証する最終 safety boundary とする。

## 4. DCI 公開範囲の設計ゲート

1 cluster 1 aggregate だけを広告すると、その aggregate に含まれる infra VIP と application VIP は同じ
reachability scope になる。次の profile を Cilium 集約試験で比較する。

| Profile | Local Fabric | DCI へ公開するもの | 必要な設計 |
|---|---|---|---|
| `aggregate-all` | `/26`／`/112` | k02／k03 の LB VIP range 全体 | aggregate に site community を付け、DCI で許可 |
| `hybrid-clustermesh-only` | `/26`／`/112` と Cluster Mesh API exact route | Cluster Mesh API の `/32`／`/128` だけ | aggregate は DCI で拒否し、site community を持つ exact route だけを許可。Cilium が両 prefix を期待どおり生成するか試験必須 |
| `exact-clustermesh-only` | Service ごとの `/32`／`/128` | Cluster Mesh API の `/32`／`/128` だけ | 現在の exact route と BGW filter を維持 |
| `split-pool` | scope ごとの aggregate | DCI 用 aggregate だけ | reachability scope ごとに整列した LB IPAM pool へ再設計 |

現在の「application VIP は site-local」という設計を維持する場合、`/26`／`/112` の aggregate を DCI まで
通してはならない。pool を変えずに Cilium 集約を試す場合は `hybrid-clustermesh-only` とし、local Fabric では
aggregate、DCI では Cluster Mesh API の more-specific exact route だけを通す。aggregate と exact route の
同時生成、community、withdraw が期待どおりであることを `AGG-02`／`AGG-04`／`AGG-06` で確認する。
本項目を `AGG-D01` とし、最終採否と同時に `Ready` へ更新する。

## 5. Cilium resource 候補

次は初期 `hybrid-clustermesh-only` の概念例であり、現在の `20-bgp.yaml` へは未反映である。
k03 では community を `65022:510` に置き換える。

```yaml
apiVersion: cilium.io/v2
kind: CiliumBGPAdvertisement
metadata:
  name: k02-loadbalancer-aggregated
  labels:
    advertise: k02-normal
spec:
  advertisements:
    - advertisementType: Service
      service:
        addresses:
          - LoadBalancerIP
        aggregationLengthIPv4: 26
        aggregationLengthIPv6: 112
      selector:
        matchLabels:
          bgp-advertise: "true"
    - advertisementType: Service
      service:
        addresses:
          - LoadBalancerIP
      selector:
        matchLabels:
          dci-export: clustermesh
      attributes:
        communities:
          standard:
            - "65012:510"
```

上記は normal profile である。planned-shut profile は同じ Service selector、aggregation length、standard
community を維持し、各 advertisement に `wellKnown: [planned-shut]` を追加する。normal／planned-shut 用の
`CiliumBGPPeerConfig` はそれぞれ一方の Advertisement だけを選び、同じ aggregate を異なる path attribute で
同時広告しない。状態遷移と session 維持の確認方法は
[Cilium BGP 経路退避とメンテナンス設計](bgp-maintenance-and-route-drain.md)を正本とする。

現在の `20-bgp.yaml` にある重複 Service selector は Cilium `1.20.1` でサポートされ、exact route の community
は一致する advertisement の和集合になる。上の hybrid 案では一般 Service advertisement だけを集約し、
Cluster Mesh API advertisement は aggregation length を指定せず exact route と site community を維持する。

ただし、複数の Service advertisement が集約によって同じ prefix を異なる path attribute で生成する動作は
公式文書で undefined とされる。両 advertisement に同じ aggregation length を設定してはならず、render 後に
aggregate と exact route の prefix／attribute を実測する。比較試験時に overlay resource を生成し、既存
resource と同時適用しない。

`externalTrafficPolicy: Local` の LoadBalancer Service では aggregation length が無視される。このため、
同じ advertisement selector に `Cluster` と `Local` Service が一致しても、`Cluster` は `/26`／`/112`、
`Local` は endpoint が存在する Node から `/32`／`/128` として広告される。BGP 終端の inbound filter は
site aggregate と LB pool 内 exact route の両方を許可する。Local exact route が aggregate より longest match で
優先され、endpoint 消失時に該当 Node の exact route だけが withdraw されることを比較試験で確認する。

## 6. 比較試験と合否基準

| Test ID | 試験 | 合格条件 |
|---|---|---|
| `AGG-00` | loop 防止 preflight | worker 2 Node の FIB で site aggregate が `blackhole` になり、BGP resource はまだ未適用である |
| `AGG-01` | resource 静的検証 | 採用 Cilium CRD schema で render／server-side dry-run に合格し、同一 aggregate を異なる attribute で生成する定義がない |
| `AGG-02` | aggregate 広告 | k02／k03 の `/26`／`/112` を広告し、hybrid では Cluster Mesh API の exact `/32`／`/128` も site community 付きで存在する。意図しない同一 prefix／異属性がない |
| `AGG-03` | 割り当て済み VIP | IPv4／IPv6 の infra／app VIP が local Fabric から到達できる |
| `AGG-04` | DCI 到達性 | `AGG-D01` で許可した scope だけが remote site から到達できる |
| `AGG-05` | 未割り当て VIP | IPv4 `.63` と IPv6 `:1:fffe` が未割り当てであることを確認してから送信し、timeout または明示 reject となる。TTL exceeded、packet 循環、counter の継続増加がない |
| `AGG-06` | Service 追加／削除 | 同じ aggregate 内に対象 Service が残る間は aggregate を維持し、最後の対象 Service 削除後に withdraw する |
| `AGG-07` | worker／session 障害 | 片 worker 停止後も残存 path で新規通信が復旧し、全 speaker 停止時は aggregate を withdraw する |
| `AGG-08` | traffic policy | `externalTrafficPolicy: Local` は endpoint がある Node から exact route を広告し、`Cluster` aggregate と共存する。FIB では exact route が優先され、endpoint 消失時に該当 Node の exact path だけが withdraw される |
| `AGG-09` | rollback | Cilium 集約を停止し、必要に応じて exact `/32`／`/128` または直接 BGP 終端集約へ戻せる |

主な判断 command は次のとおりとする。CLI version により host 側 `cilium bgp routes` が利用できない場合は、
対象 Agent Pod 内の `cilium-dbg bgp routes` を使用する。

```bash
cilium bgp peers
cilium bgp routes advertised ipv4 unicast
cilium bgp routes advertised ipv6 unicast

kubectl -n kube-system exec <cilium-pod> -- \
  cilium-dbg bgp routes advertised ipv4 unicast
kubectl -n kube-system exec <cilium-pod> -- \
  cilium-dbg bgp routes advertised ipv6 unicast
```

NX-OS では次を基本形とし、直接 BGP peer、tenant VRF、EVPN Route Type 5、DCI advertised／received route を
同一 Test ID と時刻で記録する。

```text
show bgp vrf tenant1-vpc1 ipv4 unicast summary
show bgp vrf tenant1-vpc1 ipv6 unicast summary
show bgp l2vpn evpn route-type 5
show bgp l2vpn evpn neighbors <DCI-PEER-IP> advertised-routes
show bgp l2vpn evpn neighbors <DCI-PEER-IP> routes
```

未割り当て VIP は `traceroute`／`traceroute6`、interface counter、必要に応じた packet capture を併用し、
単なる接続失敗ではなく loop がないことを判定する。

## 7. 最終選定規則

| 条件 | 採用箇所 |
|---|---|
| `aggregate-all` で `AGG-01`～`AGG-09` が合格する | Cilium aggregate |
| Cluster Mesh API だけを DCI 公開し、hybrid が全試験に合格する | Cilium aggregate と Cluster Mesh API exact route の hybrid |
| 未割り当て VIP が loop する、異なる path attribute が必要、または `Local` Service の集約が必要 | 直接 BGP 終端 |
| local Fabric では exact route が必要で、DCI 区間だけ削減したい | DCI BGW |
| Cluster Mesh API だけを DCI 公開し、hybrid が不合格で pool を再設計しない | 集約せず exact route と BGW filter を維持 |

Cilium を採用した場合も DCI BGW の import／export filter は残す。`aggregate-all` では aggregate prefix と
site community、hybrid では Cluster Mesh API exact prefix と site community を照合する。採用箇所を確定した
後にだけ、実 `CiliumBGPAdvertisement`、NX-OS route-map、`maximum-prefix`、受入手順を同じ変更単位で
更新する。

## 8. 参照 URL

- [Cilium BGP Control Plane Resources](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/)
  - Service VIP の既定 exact route、prefix aggregation field、`externalTrafficPolicy: Local` の制限、
    未割り当て VIP の routing loop、異なる path attribute の既知問題を 2026-08-29 に確認
- [Cilium PR `#37623`](https://github.com/cilium/cilium/pull/37623)
  - merge されず、後続の分割 PR を優先して 2025-08-01 に close されたことを 2026-08-29 に確認
- [Cilium PR `#40684`](https://github.com/cilium/cilium/pull/40684)
  - 存在する LoadBalancer／ClusterIP frontend の未定義 port／protocol を wildcard Service entry で drop する
    修正が merge され、Cilium `1.19.0` へ収録されたことを 2026-08-29 に確認
- [Cisco Nexus 9000 VXLAN BGP EVPN Design and Implementation Guide](https://www.cisco.com/c/en/us/td/docs/dcn/whitepapers/cisco-vxlan-bgp-evpn-design-and-implementation-guide.pdf)
  - NX-OS BGP の `aggregate-address ... summary-only` と EVPN Type 5 の設計例を 2026-08-29 に確認
