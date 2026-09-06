# Cilium ラボ試験課題台帳

## 1. 目的

この文書は、Cilium、Hubble、Tetragon の試験中に発生した問題と、その影響、切り分け、
暫定回避、恒久対処候補を継続して管理する課題台帳である。実行手順には詳細ログを重複して
記載せず、課題 ID とこの文書へのリンクを記載する。

実際の packet capture、`cilium sysdump`、機器出力などは `logs/` または `operations/` 配下の
Git 管理外領域へ保存する。この文書には、再現に必要な条件と判断根拠だけを残す。

## 2. 管理ルール

### 2.1 状態

| 状態 | 意味 |
|---|---|
| `Open` | 原因と回避策を調査中 |
| `Workaround prepared` | 回避用設定または手順を作成済みで、実環境での確認前 |
| `Workaround validated` | 回避策の合格条件を満たし、既知課題付きで後続試験を継続可能 |
| `Fix candidate` | 恒久対処候補を準備済みで比較試験前 |
| `Resolved` | 恒久対処後の再試験に合格 |
| `Closed as limitation` | 制限事項として受容し、設計上の扱いを確定 |

`Workaround validated` は元の期待動作が合格したことを意味しない。元の経路は既知課題として残し、
恒久対処後に同じ再現試験へ合格した場合だけ `Resolved` とする。

### 2.2 課題ごとに残す項目

1. 発生日、対象 Stage、component version、host kernel、datapath 条件
2. 期待結果、実際の結果、影響範囲
3. 再現条件と再現率
4. 確認済みの証拠と否定できた要因
5. 暫定原因と確度
6. 回避策、回避策固有の制約、回避策の合否基準
7. 恒久対処候補、再試験条件、終了条件
8. 参照した正式資料と upstream issue／pull request

## 3. 課題一覧

| ID | 状態 | 対象 | 症状 | 試験継続時の扱い |
|---|---|---|---|---|
| `TI-001` | `Workaround validated` | adc-k02 Stage 2A／2B | Fabric client から IPv6 NodePort `externalTrafficPolicy: Cluster` へ接続した場合、remote backend 選択時だけ応答が timeout する | 両 worker の VXLAN TX checksum off で回帰確認済み。恒久 kernel 対応は未実施 |
| `TI-002` | `Open` | adc-k02 Stage 2A BGP／Fabric | Cilium Service route は BGP／RIB／EVPN に存在するが、Nexus 9000v の Forwarding 表では aggregate が欠落し、BGR の exact route も 1 path だけに見える | 基本通信と観測試験は継続し、Forwarding／ECMP 冗長性は合格にしない |
| `TI-003` | `Workaround validated` | adc-k02 NP-05 | 内部 Service DNS は成功するが、CoreDNS から外部上流 DNS への query が失敗する | Pod 到達確認済み resolver を CoreDNS `forward` へ runtime 設定し、FQDN Policy の許可／拒否通信を確認済み |
| `TI-004` | `Open` | adc-k02 Stage 1／2B | 大きい TCP／UDP が Gateway 経由・通常経路で失敗し、高負荷後に LB が一時 timeout | 小さい通信の成功と分離し、サーバ側 Leaf を MTU 9216 へ修正し、8,900 byte まで再確認済み。高レート UDP の損失を継続確認、SNAT port 枯渇は保留 |
| `TI-005` | `Open` | adc-k02 Stage 1／2B | Node 間 VXLAN が Fabric ではなく管理側 eth0 を通る設計差分 | 実経路を保存。Node InternalIP／underlay の変更は別作業として保留 |
| `TI-006` | `Open` | adc-k02 W-EGRESS-06 | 手順再現時、新規 Pod の最初の IPv4 接続だけ短い deadline で timeout | 239/240 成功、後続安定。初期 timeout の原因は未確定 |
| `TI-007` | `Open` | Leaf Po11〜16／Stage 1・2B | Node／他サーバ向け MTU 9100 の統一が未実施、9000 byte 境界が未検証 | 次回の最優先。system jumbo の影響確認後に config 修正・適用・再試験 |

## 4. TI-001: IPv6 NodePort の remote backend 応答 checksum 不整合

**2026-09-06 の更新：** 両 worker の `cilium_vxlan tx-checksum-ip-generic=off` を適用し、
[Egress・LB・限定 CLI の回帰](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/offload-regression-result.md) が成功した。
状態を `Workaround validated` とする。[設定維持・復旧の運用](checksum-compat-operations.md) も整備済み。
kernel 更新・Node 再起動は実施せず、恒久修正完了とはしない。以降の `Workaround prepared` という記載はこの更新前の調査履歴である。
大きい packet／高負荷の問題は別件 `TI-004` として管理する。

### 4.1 環境と再現条件

| 項目 | 値 |
|---|---|
| 発生日 | 2026-08-30 |
| Cluster | `adc-k02` |
| Kubernetes | `v1.35.5` |
| Cilium | `v1.20.1` |
| Host kernel | `5.14.0-611.27.1.el9_7.x86_64` |
| Datapath | VXLAN、kube-proxy replacement、BPF host routing |
| Service | dual-stack NodePort、`externalTrafficPolicy: Cluster` |
| Client | NX-OS Fabric 側の外部 client |

Fabric client から worker の Fabric IPv6 Node address と NodePort へ新規 TCP connection を繰り返す。
NodePort を受信した worker と同じ Node の backend が選択された場合は成功し、別 worker の backend が
選択された場合は timeout する。IPv4 の同じ試験は成功する。

### 4.2 期待結果と影響

期待結果は、`externalTrafficPolicy: Cluster` により ingress Node に関係なく、local／remote の両 backend へ
IPv6 NodePort 通信が成功することである。

現時点で確認した直接の影響は、外部から ingress する IPv6 TCP Service が remote backend を選択する経路である。
同じ eBPF Service LB path を使用する `externalTrafficPolicy: Cluster` の IPv6 LoadBalancer も、同じ観点で
確認が必要である。Cluster 内の dual-stack ClusterIP、IPv4／IPv6 Pod 間通信、Cilium health は正常である。

### 4.3 確認できた証拠

| 確認項目 | 結果 |
|---|---|
| Fabric route／NDP／Node への IPv6 ICMP | 正常 |
| NodePort の local backend | 成功 |
| NodePort の remote backend | timeout |
| backend の IPv4／IPv6 listen | `0.0.0.0:8080` と `[::]:8080` を確認 |
| Pod 間 IPv4／IPv6 | same-node／cross-node とも成功 |
| Cilium health | 3／3 Node の host／endpoint IPv4／IPv6 が到達可能 |
| Cilium Service map | 両 backend が `active` |
| Cilium drop monitor | 該当 packet の drop を確認せず |
| Cilium CT／NAT map | remote response の到達と reverse NAT entry を確認 |
| 外部 client の packet capture | local backend の SYN-ACK は checksum 正常、remote backend の SYN-ACK は checksum 不正 |
| Ethernet destination | 成功時／失敗時とも期待する next-hop MAC |
| 失敗時の checksum 差分 | 観測した packet では一定の `0x7f45` |

### 4.4 否定または優先度を下げた要因

- Fabric route、VLAN／VNI、NDP、next-hop MAC の不整合
- backend application の IPv6 待受不足
- Pod 間 IPv6 overlay 全体の障害
- Cilium Service map への remote backend 未登録
- Cilium policy drop
- `bond0.<VLAN>` の TX checksum／GSO／TSO offload 単独の問題
- BPF host routing 固有の問題

offload を一時無効化しても remote backend だけ失敗した。`bpf.hostLegacyRouting=true` へ一時変更しても
成功率は改善せず、通常 values を再適用した。この 2 つを回避策には採用しない。

後続試験前に、通常 values への復帰と Cilium の Ready を確認する。全 Cilium Pod の `Routing` が
`Host: BPF` であることを baseline とする。

```bash
cilium status --context "${KUBE_CONTEXT}" --wait

for CILIUM_POD in $(kubectl --context "${KUBE_CONTEXT}" -n kube-system \
  get pod -l k8s-app=cilium -o name)
do
  echo "### ${CILIUM_POD}"
  kubectl --context "${KUBE_CONTEXT}" -n kube-system \
    exec "${CILIUM_POD}" -- cilium-dbg status --verbose | \
    grep '^Routing:'
done
```

### 4.5 暫定原因

Cilium `v1.20.1` が、`BPF_F_IPV6` を持たない RHEL 9.7 の 5.14 系 kernel で使用する IPv6 checksum の
fallback path と、VXLAN をまたぐ IPv6 NodePort reverse NAT の組み合わせが暫定原因の有力候補である。

Cilium の IPv6 underlay checksum 修正には、`BPF_F_IPV6` を使用する経路と旧 kernel 向け fallback がある。
ただし、このラボ固有の upstream defect と断定するには、該当 kernel capability を持つ新しい host kernel での
比較、または upstream による再現確認が必要である。

### 4.6 試験継続用の回避策

外部 IPv6 Service の基本試験は `externalTrafficPolicy: Local` で継続する。次の 2 Service を使用する。

- NodePort: `lab-smoke-nodeport-local`
- LoadBalancer: `lab-smoke-lb-local`

`externalTrafficPolicy: Local` は ingress Node 上の local endpoint だけへ転送するため、今回の remote backend path を
使用しない。一方、endpoint のない Node で受信した NodePort は成功しない。Cilium BGP Control Plane は Local
LoadBalancer VIP を local endpoint を持つ Node だけから exact route として広告するため、BGP route の広告／withdraw
も回避策の一部として確認する。

`lab-smoke-nodeport` と `lab-smoke-lb-cluster` は削除せず、元の期待動作を再現する regression 用 Service として残す。

2026-08-30 に `lab-smoke-nodeport-local` の作成、Cilium／Operator／Envoy／Hubble の Ready、全 3 Node の
`Routing: Network: Tunnel [vxlan] Host: BPF` への復帰を確認した。

同日、Fabric client から Local NodePort へ次の連続通信を実施し、合計 80／80 request が成功した。

| Target | Address family | 回数 | 応答 backend | 結果 |
|---|---|---:|---|---|
| `adc-k02-worker` | IPv4 `172.16.4.21` | 20 | `lab-smoke-7d7bb8cdc7-sgxzw` | 20／20 成功 |
| `adc-k02-worker2` | IPv4 `172.16.4.22` | 20 | `lab-smoke-7d7bb8cdc7-hpt4c` | 20／20 成功 |
| `adc-k02-worker` | IPv6 `fd21:0:0:4::2:1` | 20 | `lab-smoke-7d7bb8cdc7-sgxzw` | 20／20 成功 |
| `adc-k02-worker2` | IPv6 `fd21:0:0:4::2:2` | 20 | `lab-smoke-7d7bb8cdc7-hpt4c` | 20／20 成功 |

各 Node address の応答は同じ Node 上の local backend と一致した。Cluster NodePort の単発確認は
IPv4／IPv6 とも成功したが、過去の連続試験では IPv6 remote backend 選択時に断続的な失敗を確認しているため、
単発成功を `TI-001` の解消根拠にはしない。

Local NodePort の回避策確認は合格した。LoadBalancer と BGP route の結果は次に記載する。

同日、LoadBalancer Service の連続通信と Cilium／ADC BGR の BGP route を確認した。

| Service path | IPv4 | IPv6 | 結果 |
|---|---:|---:|---|
| Cluster LoadBalancer | 20／20 成功 | 9／20 成功、11／20 timeout | IPv6 で `TI-001` を再現 |
| Local LoadBalancer | 20／20 成功 | 20／20 成功 | 回避通信は合格 |

Cilium は Cluster VIP を IPv4 `/26`／IPv6 `/112` aggregate、Local VIP を IPv4 `/32`／IPv6 `/128` exact route
として、worker 2 Node から両 ADC BGR peer へ広告していた。ADC BGR 2 台は aggregate と exact route の双方で
worker 2 Node を eBGP multipath として保持し、BGP table の `in HW` を確認した。IPv4 RIB も 2 next-hop を保持した。

初回確認では IPv6 BGP table が 2 next-hop を保持していたが、IPv6 VIP に対して `show ip route` を
実行したため、IPv6 RIB は未確認であった。

再実行により、ADC BGR 2 台の IPv6 RIB でも aggregate／exact route と worker 2 Node の next-hop を確認した。
ADC Leaf 1／2 では、IPv4 `/26`／`/32` と IPv6 `/112`／`/128` の EVPN Type-5、tenant VRF の IPv4／IPv6 RIB、
各 Leaf から local BGR 方向の next-hop を確認した。Local exact route の FIB は IPv4／IPv6 とも
`Partial Install: No` であった。

BGR／Leaf の全 4 台で aggregate prefix 自体を `detail`／`platform` 付きで指定したが、IPv4／IPv6 とも
`no exact match` になった。BGR の Local exact route は `Partial Install: No` である一方、RIB の 2 path に対して
Forwarding 表では worker1 の 1 path だけが表示され、ECMP object も表示されなかった。この RIB／Forwarding 表の
不一致は [`TI-002`](#5-ti-002-nexus-9000v-の-cilium-bgp-route-における-ribforwarding-表不一致)へ分離し、
`TI-001` の状態は `Workaround prepared` のままとする。

#### 回避策の合格条件

1. worker 2 Node に backend を 1 Pod ずつ配置した状態で、両 worker の Local NodePort に対する IPv4／IPv6 TCP 接続が各 20 回連続で成功する。
2. Local LoadBalancer VIP に対する IPv4／IPv6 TCP 接続が各 20 回連続で成功する。
3. 応答 hostname が ingress Node の local backend と一致する。
4. Local LoadBalancer の `/32`／`/128` が local endpoint を持つ Node だけから広告される。
5. ClusterIP、Pod 間通信、Cilium health に regression がない。

合格後に状態を `Workaround validated` へ変更し、後続の Hubble、Tetragon、Network Policy 試験を継続する。

### 4.7 恒久対処候補

優先順は次のとおりとする。

1. `BPF_F_IPV6` と関連する stable fix を含む新しい host kernel で、同じ Cilium values と workload を比較する。
2. 現行 kernel と比較 kernel の `cilium sysdump`、最小再現手順、packet capture を揃えて upstream へ報告する。
3. upstream の判断に従い、Cilium patch release または kernel update を適用して Cluster Service を再試験する。
4. DSR など別の Service forwarding mode は設計変更を伴う比較項目とし、即時の回避策にはしない。

kind Node image を変更しても Node container は host kernel を共有するため、kernel capability の比較にはならない。

#### `Resolved` の条件

- `externalTrafficPolicy: Cluster` の IPv6 NodePort と LoadBalancer で、local／remote backend を明示的に確認しながら各 100 回連続で成功する。
- external packet capture で remote backend 応答の TCP checksum が正常である。
- IPv4、ClusterIP、Pod 間通信、BGP route に regression がない。
- 採用した Cilium／kernel version と根拠を version baseline と参照 URL 台帳へ反映する。

### 4.8 追加で行う切り分け

後続試験を止めず、次の順で実施する。

| 優先度 | 項目 | 目的 |
|---|---|---|
| 完了 | IPv6 LoadBalancer `Cluster` と `Local` の比較 | Cluster IPv6 は 9／20 成功、Local IPv6 は 20／20 成功 |
| 完了 | Local NodePort／LoadBalancer の連続試験 | NodePort 80／80、LoadBalancer IPv4／IPv6 各 20／20 成功 |
| 必須 | endpoint を 1 Node に限定した BGP route／withdraw | endpoint のない Node が Local VIP を広告しないことを確認する |
| 推奨 | 再現直後の `cilium sysdump` 保存 | upstream 報告用の状態を環境変更前に保持する |
| 推奨 | IPv6 UDP の local／remote backend 比較 | TCP 固有か L4 checksum 全般かを切り分ける |
| 後続 | 新しい host kernel との A/B 比較 | kernel capability／stable fix との因果を確認する |

現時点では、offload と Host Legacy Routing の再試験を繰り返す優先度は低い。

### 4.9 正式資料と upstream 情報

- [Cilium System Requirements](https://docs.cilium.io/en/stable/operations/system_requirements/)
- [Cilium Helm Reference](https://docs.cilium.io/en/stable/helm-values/)
- [Cilium BGP Control Plane: Prefix Aggregation](https://docs.cilium.io/en/stable/network/bgp-control-plane/bgp-control-plane-configuration/#prefix-aggregation)
- [Cilium PR #39279: Workaround IPv6 underlay checksum issue](https://github.com/cilium/cilium/pull/39279)
- [Cilium PR #39631: Use long-term solution for IPv6 tunneling checksum bug](https://github.com/cilium/cilium/pull/39631)
- [Cilium v1.20.1 `lb.h`](https://github.com/cilium/cilium/blob/v1.20.1/bpf/lib/lb.h)
- [Linux stable patch: Fix L4 csum update on IPv6 in `CHECKSUM_COMPLETE`](https://www.spinics.net/lists/netdev/msg1099852.html)

### 4.10 切り分け再開時の引継ぎ

課題 ID は数字 `1` の `T1-001` ではなく、大文字 `I` を使用した `TI-001` である。別の作業 session で
再開する場合は、次のように依頼する。

```text
nxos_fabric/docs/cilium-lab/test-issue-register.md の TI-001 を読み、
「4.10 切り分け再開時の引継ぎ」の未完了項目から切り分けを再開してください。
```

この文書の 4.1 から 4.9 に、再現環境、影響範囲、観測済みの packet／BPF 証拠、否定した要因、
原因仮説、回避策、正式資料、恒久対処候補を記載している。再開時は、offload 無効化と
`bpf.hostLegacyRouting=true` の比較を繰り返さず、次の境界から開始する。

#### 完了済み

- Cilium `v1.20.1`／Kubernetes `v1.35.5`／host kernel `5.14.0-611.27.1.el9_7.x86_64` の条件を記録
- Cluster 内の IPv4／IPv6 ClusterIP、same-node／cross-node Pod 通信、Cilium health を確認
- Fabric route／NDP、backend listen、Service map、CT／NAT、drop monitor を確認
- 成功 packet と失敗 packet の checksum、next-hop MAC、一定の checksum 差分を比較
- NIC offload と Host Legacy Routing が主要因でないことを確認
- 通常 values を再適用し、全 3 Node が `Host: BPF` へ復帰
- `lab-smoke-nodeport-local` を作成
- Local NodePort の IPv4／IPv6、2 Node、合計 80／80 request が成功
- Cluster LoadBalancer は IPv4 20／20 成功、IPv6 9／20 成功、11／20 timeout で `TI-001` を再現
- Local LoadBalancer は IPv4／IPv6 とも 20／20 request が成功
- Cilium は Cluster VIP の aggregate と Local VIP の exact route を worker 2 Node から両 BGR へ広告
- ADC BGR 2 台の BGP table で aggregate／exact route、2 eBGP path、`in HW` を確認
- ADC BGR 2 台の IPv4 RIB で worker 2 Node の next-hop を確認
- ADC BGR 2 台の IPv6 RIB で worker 2 Node の next-hop を確認
- ADC Leaf 1／2 で IPv4／IPv6 aggregate／exact EVPN Type-5 と RIB を確認
- ADC Leaf 1／2 の Local exact FIB で expected next-hop と `Partial Install: No` を確認
- ADC BGR／Leaf の全 4 台で aggregate／exact prefix を直接指定した IPv4／IPv6 Forwarding detail を確認
- Aggregate の `no exact match` と BGR exact route の 1 path 表示を `TI-002` へ分離

#### 未完了

1. backend を 1 Node に限定した Local VIP の広告停止／withdraw 確認
2. IPv6 UDP の local／remote backend 比較
3. `BPF_F_IPV6` と関連 stable fix を含む host kernel との A／B 比較
4. 必要に応じた upstream issue の作成

通常の Stage 2A 試験を進める場合は、
[lab-smoke 実行手順の「9. Hubble flow」](../../nxos_singlesite/k8s_kind/k02/cilium/manifests/validation/lab-smoke/README.md)から再開する。
原因切り分けを再開する場合は、Cluster NodePort／LoadBalancer の連続試験で remote backend の失敗を再現し、
現行 kernel と比較 kernel の同一条件 A／B 試験へ進む。

#### Git 管理外で保持する証拠

生の packet capture、`cilium sysdump`、機器出力はこの文書には含まれない。upstream 報告または kernel 比較を
予定する場合は、環境変更前に `operations/cilium-lab/TI-001/` へ保存し、取得日時、試験条件、file name、
SHA256 を作業記録へ残す。この directory は Git へ追加しない。

```bash
mkdir -p operations/cilium-lab/TI-001

cilium sysdump \
  --context "${KUBE_CONTEXT}" \
  --output-filename operations/cilium-lab/TI-001/adc-k02-before-kernel-ab
```

現時点では、今回取得した生の packet capture と `cilium sysdump` の永続保存は未確認である。文書だけで
論理的な切り分けは再開できるが、upstream へ証拠を提出する場合は生データを改めて取得する。

## 5. TI-002: Nexus 9000v の Cilium BGP route における RIB／Forwarding 表不一致

### 5.1 環境と影響範囲

| 項目 | 値 |
|---|---|
| 発生日 | 2026-08-30 |
| Cluster | `adc-k02` |
| Cilium | `v1.20.1` |
| NX-OS | Nexus 9000v `10.5(4)` |
| BGR | `adc-bgrt0101`、`adc-bgrt0102` |
| Leaf | `adc-lfsw0101`、`adc-lfsw0102` |
| VRF | `tenant1-vpc1` |
| Cluster aggregate | IPv4 `172.16.14.0/26`、IPv6 `fd21::14:0:0:1:0/112` |
| 確認した Local exact route | IPv4 `172.16.14.21/32`、IPv6 `fd21::14:0:0:1:101/128` |

この課題は Cilium BGP advertisement、NX-OS BGP／RIB／EVPN と Nexus 9000v software data plane の境界を
対象とする。`TI-001` の IPv6 Service datapath checksum 問題とは分離して管理する。

### 5.2 確認できた事実

| 確認箇所 | Aggregate `/26`／`/112` | Local exact `/32`／`/128` |
|---|---|---|
| Cilium BGP route | worker 2 Node から広告 | worker 2 Node から広告 |
| ADC BGR BGP table | 2 eBGP path、`in HW` | 2 eBGP path、`in HW` |
| ADC BGR RIB | worker 2 Node の next-hop | worker 2 Node の next-hop |
| ADC Leaf EVPN／RIB | Type-5 と tenant RIB に存在 | Type-5 と tenant RIB に存在 |
| ADC BGR Forwarding | `no exact match` | worker1 の 1 path、`Partial Install: No` |
| ADC Leaf Forwarding | `no exact match` | local BGR の 1 path、`Partial Install: No` |

ADC BGR 2 台で `show forwarding ... route partial` に該当 route はなく、`unresolved` にも Service route は
表示されなかった。`show forwarding ecmp platform` と `show forwarding ecmp partial` も ECMP object を
表示しなかった。したがって、aggregate の欠落は partial install または unresolved next-hop だけでは説明できない。

Local exact route の `platform` 出力は `Hw-idx` が `0x0` であった。Nexus 9000v は特定 ASIC を
emulate せず software data plane を使用するため、この値だけで hardware programming failure とは断定しない。
一方、公式の Nexus 9000v `10.5(x)` guide では ECMP は support 対象であるため、1 path 表示を仕様として
受容する前に実通信と route withdraw で動作を確認する。

### 5.3 現時点の判定

- Cilium advertisement、ADC BGR の BGP／RIB、ADC Leaf の EVPN Type-5／RIB は合格
- Local LoadBalancer の IPv4／IPv6 基本通信は合格
- Aggregate と BGR ECMP の Forwarding 表受入は未合格
- Nexus 9000v の表示差か、software data plane の single-path programming かは未確定
- Hubble、Tetragon、Network Policy の機能試験は継続できる
- BGP／Node 障害時の冗長性は、この課題の切り分け完了前に合格としない

### 5.4 次に行う確認

ADC BGR 2 台で、RIB と Forwarding の inconsistency check を取得する。

```text
terminal length 0

show forwarding ipv4 unicast inconsistency suppress-transient vrf tenant1-vpc1
show forwarding ipv6 unicast inconsistency suppress-transient vrf tenant1-vpc1
```

次に、Fabric client から Local VIP へ複数の新規 connection を作成し、Hubble で ingress Node と backend の
分布を確認する。応答分布だけでは ECMP hash により一方へ偏る可能性があるため、最終確認は worker1 の
`bgp-speaker` label を一時的に外す controlled withdraw 試験で行う。

controlled withdraw では次を合格条件とする。

1. worker1 の BGP session／route が期待時間内に withdraw される。
2. BGR の BGP／RIB next-hop が worker2 へ収束する。
3. Local VIP の IPv4／IPv6 新規 connection が worker2 で成功する。
4. worker1 を復旧すると 2 path BGP／RIB へ戻る。
5. 各時点の Forwarding 表、ECMP 表、Hubble ingress Node を記録する。

### 5.5 正式資料

- [Cisco Nexus 9000v `10.5(x)` Guide](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/configuration/n9000v-9300v-9500v/cisco-nexus-9000v-9300v-9500v-guide-release-105x/m-overview.html)
- [Nexus 9000 NX-OS `10.5(x)` F Show Commands](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/105x/command-reference/show/b_n9k_show_commands_1051/m_f_showcmds.html)

### 5.6 切り分け再開時の引継ぎ

別の作業 session で再開する場合は、次のように依頼する。

```text
nxos_fabric/docs/cilium-lab/test-issue-register.md の TI-002 を読み、
「5.4 次に行う確認」から RIB／Forwarding／ECMP の切り分けを再開してください。
```

機器の生出力は `operations/cilium-lab/TI-002/` へ Git 管理外で保存し、この文書には判定に必要な
要約だけを反映する。

## 6. TI-003: Kind 上の CoreDNS upstream 到達不可

### 6.1 症状と影響

2026-08-30 の single-site `adc-k02` における `NP-05` で、
`kubernetes.default.svc.cluster.local` は解決できる一方、`www.example.com` と `www.example.net` は
Policy 対象 Pod と対象外 Pod の双方で解決できなかった。CiliumNetworkPolicy は `VALID=True` であり、Pod から
CoreDNS への UDP `53` は Hubble で `ALLOWED`／`FORWARDED` だった。

この課題は外部 FQDN Policy の前提条件に影響する。内部 Service DNS、Cilium DNS Proxy rule の validation、
および Pod → CoreDNS の datapath 障害とは分離して扱う。

### 6.2 切り分け結果

| 確認項目 | 結果 |
|---|---|
| 内部 Service DNS | 成功 |
| Policy 対象 Pod の外部 DNS | 失敗 |
| Policy 対象外 Pod の外部 DNS | 失敗 |
| Pod → CoreDNS Hubble flow | `ALLOWED`／`FORWARDED` |
| Cilium BPF masquerade | IPv4／IPv6 とも有効 |
| CoreDNS placement | 2 Pod とも `adc-k02-worker` |
| CoreDNS 既定 upstream | Kind Node 内の `/etc/resolv.conf` を経由 |
| host resolver を直接指定した一時 Pod | `www.example.com` の AAAA 応答取得に成功 |
| runtime resolver 適用後の直達試験 | 成功 |
| runtime resolver 適用後の Cluster DNS 試験 | 成功 |

一時 Pod は `dnsPolicy: None` とし、host `/etc/resolv.conf` から得た resolver を `dnsConfig.nameservers` へ
指定した。これが成功したため、外部 DNS 自体や Fabric 外向き経路ではなく、CoreDNS が継承した Kind／Docker
resolver への転送経路を暫定原因とする。

### 6.3 回避策と可搬性

[`configure-coredns-upstream.sh`](../../scripts/cilium-lab/configure-coredns-upstream.sh) で次を自動化する。

1. `--upstream`、`COREDNS_UPSTREAM_DNS`、host `/etc/resolv.conf` の順で非 loopback IPv4 resolver を選定する。
2. 一時 Pod から採用候補 resolver へ直接 query し、応答がない値は適用しない。
3. CoreDNS ConfigMap の `forward .` だけを置換して CoreDNS を rollout する。
4. Cluster DNS 経由の外部名を再確認し、失敗時は元の Corefile へ戻す。
5. 採用値を site 別の `cilium/runtime/20-coredns-upstream.env` へ記録する。この file は Git 管理外とする。

環境固有 resolver は追跡対象の manifest／文書へ固定しない。single-site／multi-site、実行 host ごとに
check-only の出力と Pod 直達試験を通して選定する。

2026-08-30 に single-site `adc-k02` で check-only の差分を確認後、runtime resolver を CoreDNS の
`forward` へ適用した。スクリプト内の Pod 直達試験と Cluster DNS 試験はいずれも成功し、採用値は Git 管理外の
site 別 runtime file に記録された。rollback は発生していない。

続けて `NP-05` を再実行し、許可対象と非許可対象の両 FQDN が名前解決できる状態で、許可対象は HTTP `200`、
非許可対象は HTTP `000`／終了 code `28` の timeout となった。DNS upstream 障害による timeout ではなく、
名前解決後の FQDN Policy による通信制御を確認できたため、回避策を `Workaround validated` とする。

Hubble では両 FQDN の A／AAAA query と応答が `FORWARDED`、許可対象の TCP `80` が
`ALLOWED`／`FORWARDED`、非許可対象の TCP SYN が `Policy denied DROPPED` となった。同じ Node の Cilium Agent
FQDN cache には両 FQDN の A／AAAA 応答と TTL が登録された。これにより `NP-05` 全体も合格した。

状態を `Workaround validated` へ変更する条件は、スクリプトの `--apply` が成功し、CoreDNS 経由で許可・非許可の
両 FQDN が名前解決でき、`NP-05` で許可先 HTTP だけが成功することである。この条件は 2026-08-30 に合格した。
恒久的に Node の resolver 継承を設計する場合は、Kind／kubelet の `resolv.conf` 指定との比較を別途行う。

### 6.4 正式資料

- [Kubernetes: Customizing DNS Service](https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/)
- [Kubernetes: Debugging DNS Resolution](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/)
- [Cilium: DNS Policy and IP Discovery](https://docs.cilium.io/en/stable/security/policy/layer7/#dns-policy-and-ip-discovery)

### 6.5 切り分け再開時の引継ぎ

別の作業 session では次のように依頼する。

```text
nxos_fabric/docs/cilium-lab/test-issue-register.md の TI-003 を読み、
CoreDNS upstream の check-only から NP-05 の再試験を再開してください。
```

<a id="ti-004-large-packets"></a>

## 7. TI-004：大きい TCP／UDP の失敗と負荷時の損失

**2026-09-06 の記録への追加：** サーバ向け Po11 の MTU を修正し、[修正後の再試験](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-fix-result.md) を実施した。
1,500 byte 境界は解消し、全 180 packet と低レート 18 条件が成功。高レート UDP の損失は残るため本件は `Open` を維持する。
以下の 7.1〜7.4 は修正前の切り分け記録、7.5 が修正後の結果である。

### 7.1 事象・影響

**試験記録日：2026-09-06。** single-site k02 の Egress 残項目で検出した。実際の取得は JST で 2026-09-07 にまたがるが、依頼に従い `2026-09-06` 配下へ保存する。Cilium 1.20.1、kernel
`5.14.0-611.27.1.el9_7.x86_64`、VXLAN checksum off と既存監視を維持した状態。
[実行コマンド・結果・証跡](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-remaining-result.md) を参照する。

- 256 KiB 単位の TCP 転送は、gw-a／gw-b／Policy なし、IPv4／IPv6、1／4 接続、各 2 回の全 24 条件で完全な echo block を回収できず失敗した。
- UDP 20 Mbps の 1,200 byte は大きな未回収率、8,000 byte は全条件で応答を回収できなかった。
- 負荷後に IPv4 LB が 1 回 timeout した。負荷停止後の連続 12 HTTP と撤去前後の 8 HTTP は成功した。失敗と負荷の因果関係・内部 drop 理由は未確定。
- 小さい HTTP、SNAT の送信元・選択条件、BGP と checksum 回避策は確認できている。これを大容量性能の成功へ拡張しない。

### 7.2 確認済みの切り分け

| 比較 | 実測 | 解釈 |
|---|---|---|
| 同じ転送プログラムをサーバ内 loopback で実行 | IPv4／IPv6 とも 256 KiB 転送成功 | プログラムが大きい block を全く処理できないという可能性を下げる |
| gw-a、通常 MSS → 試験 socket の MSS 1200 | 通常は失敗、1200 は成功。両 family、2 回同じ結果 | パケットサイズ依存性がある。恒久 MSS 設定は変更していない |
| UDP 0.1 Mbps、1,200／1,400／8,000 byte | 小さい 2 条件は全応答、大きい条件は応答なし | 高負荷時の損失だけでは説明できない |
| Gateway と外部サーバの capture | Gateway では約 8.9 KB payload を送出、外部では小さい再送だけを観測 | Gateway → 外部区間のサイズ依存の損失を疑う。当初は機器単位で未確定。追加の境界測定で下記の Leaf サーバ向け区間へ限定 |
| Policy なしの比較 | 同様に失敗 | Egress Gateway 固有とは断定できない |

Node 間 VXLAN は管理側 eth0（MTU 1500）、cilium_vxlan は MTU 9000、Fabric bond／VLAN は MTU 9100。
この設計差分は是正候補だが、Gateway の Fabric NIC まで到達した大きいパケットもあるため、eth0 の値だけを原因と断定しない。
仮想 Fabric の転送能力、各区間の MTU、PMTUD、fragment／GSO の扱いを分けて確認する。

### 7.3 2026-09-06 記録への追加：サイズ境界と Leaf の MTU 不一致

[MTU 境界の結果・実行コマンド・証跡](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-result.md)。
3 経路（gw-a／gw-b／通常）× 2 family × 10 サイズ、各 3 packet を送信した。

| 確認 | 結果 | 判断 |
|---|---|---|
| IP 全長 1,400／1,499／1,500 byte | 全経路・両 family で各 3/3 echo | 少なくとも測定条件でこのサイズまで通過 |
| IP 全長 1,501〜8,900 byte | 全条件で各 0/3。write 成功後 read timeout | 高負荷なしでもサイズ依存の失敗が再現 |
| Leaf0103／0104 の Node 向け Ethernet1/6 | MTU 9216。大きい packet も eth6／tap6 に到着 | Gateway から Leaf 入口まで届く |
| 同 Leaf の server 向け port-channel11／Ethernet1/1 | MTU 1500。tap1／eth1 と server で大きい packet を観測せず | 1,500 byte の出力 MTU と失敗境界が一致 |
| ICMP と capture drop | 取得範囲に fragmentation needed／Packet Too Big なし。11 capture とも kernel drop 0 | PMTUD による回復を確認できない。ICMP 未観測は永続的な非生成の断定ではない |

**原因の判断：** 今回の大きい packet の失敗は、外部サーバ向け Leaf の MTU 1500 と jumbo を送る側の不整合で説明できる。
Node 側 9216、Node Fabric 9100、server bond 9000 に対し、server 側 port-channel／member が 1500 のままだった。
BPF／NAT の設定変更や kernel 更新を行う前に、このリンクの MTU 設計を合わせる対象が明確になった。
変更後の再試験はまだ行っていないため `Open` を維持する。

**対応済み：** 低レート測定、Leaf 前後の同時 capture、実 interface MTU 確認、コマンド・ソース・ハッシュの保存。
試験用リソースは撤去し、通常通信と LB／BGP、既存 checksum 回避策の維持を確認する。
**未対応：** server 側 MTU 修正、PMTUD／大容量 TCP・UDP の再試験、高送出レート時の損失と一時 LB timeout の原因確定。
管理 eth0 を VXLAN underlay に使う設計差分も別に残る。今回の MTU 不一致だけで全問題の原因が確定したとはしない。

### 7.4 修正前に立てた対応計画と終了条件

1. `adc-lfsw0103`／`0104` の server 向け `port-channel11` と member `Ethernet1/1` の MTU を、対向 server・SVI と合わせて設計し直す。jumbo を通す方針なら Node 側同様 9216 が候補。config 修正・投入は今回未実施。
2. Node InternalIP／VXLAN underlay の設計不一致を別途整理する。Node 再起動・kernel 変更は今回保留のまま。
3. 通常 MSS の大きい TCP／UDP が成功した後、段階的な送出量で性能を比較する。
4. 既存 LB／BGP の前後比較が安定し、通常経路の損失を説明できてから SNAT port 枯渇を再開する。

通常設定での再試験が成功するまで `Open` を維持する。試験 socket の MSS 制限だけを恒久修正や環境全体の回避策と認定しない。


### 7.5 2026-09-06：Leaf MTU 修正と再試験

- 修正対象：single-site の `adc-lfsw0103`／`0104`、サーバ 0102 向け `port-channel11`。MTU を 1500 → 9216 とし、メンバー `Ethernet1/1` の実 MTU 9216 への追従を確認した。
- 稼働中メンバーへの直接 `mtu` 指定は NX-OS に拒否されたため、Po11 側から適用した。最初の拒否・撤回の証跡も保持した。
- single-site と multisite の `as-equals`／`as-changes`、計 6 config に反映。multisite はファイルのみ。running-config は変更したが startup-config の保存は実施していない。
- gw-a／gw-b／通常経路、両 family、IP 全長 1,400〜8,900 byte の 60 条件／180 packet がすべて echo 成功。
- 通常 MSS の TCP 256 KiB と低レート UDP 1,200／8,000 byte の 18 条件も全量回収。MTU 不一致によるサイズ依存の blackhole は測定範囲で解消した。
- 以前と同じ 48 条件の高レート比較を再実施し、TCP は 23/24 条件で全量回収、UDP の未回収率は 0.00〜100.00% だった。受信量の詳細は [再試験結果](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-fix-result.md) を参照する。
- UDP 20 Mbps では損失が残り、高負荷比較中の TCP 1 条件でも sent_bytes=0／errors=1 を観測した。負荷停止後の TCP 再確認 2 回は成功。通常経路の高負荷比較後に IPv4 LB も 1 回 timeout したが、10 秒待機後の 4 宛先確認とその後は成功した。元の失敗と復旧結果を分けて保持する。次は送出レートと packet 数を段階的に変え、仮想 Fabric の転送能力・queue/drop を照合する。MTU 修正で性能受入全体まで合格とはしない。

試験専用リソースを撤去し、Leaf の修正 MTU と既存 checksum 回避策は維持する。Node 障害・復旧、kernel 更新、SNAT port 枯渇は今回実施しない。


<a id="ti-005-vxlan-underlay"></a>

## 8. TI-005：Node InternalIP と VXLAN underlay の設計差分

**試験記録日：2026-09-06、状態：Open。**
[実経路の確認結果](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-remaining-result.md#4-経路照合と-bpf-map-の実行例) と
[追加の packet capture](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-result.md) に基づく。

- 計画：Node 間の Fabric 接続と管理側接続を分離して設計・評価する。
- 実測：selected の worker2 → Gateway worker は、Node InternalIP `172.18.0.6 → 172.18.0.2` の VXLAN／`eth0`。Gateway → 外部は `bond0.14` の Fabric。
- 影響：小さい Egress HTTP は成功するが、Node 間区間を Fabric の経路・MTU・障害ドメインとして評価できない。管理側 HostPort の自動宛先選択とは別の datapath 設計の確認項目。
- 対応済み：BPF map、Node route、同じ接続の capture を照合し、実構成図と手順へ反映。
- 未対応：kubelet Node IP、Cilium の Node address／device 選択、BGP next-hop、API 到達性に対する変更設計と実装。
- 次の方針：Fabric を underlay にする場合の変更影響を整理し、別の実施枠で確認する。Node／containerlab 再起動と kernel 変更は今回実施しない。

`TI-004` の server 側 Leaf MTU 1500 は今回 packet を失った区間として確認できたため、
管理 eth0 の MTU 1500 だけを大きい通信の失敗原因とはしない。設計に合わせた underlay へ変更し、packet capture と正常なサイズ境界を確認するまで本件は未完了とする。


<a id="ti-006-newborn-first-request"></a>

## 9. TI-006：新規 Pod の最初の接続 timeout

**試験記録日：2026-09-06、状態：Open（原因未確定）。**
[手順再現の原本](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/raw/egress-extended-DWwwrvhj/newborn/1.jsonl) と
[結果報告](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-result.md) に保存する。

新規 Pod 3 個 × 2 family × 40 回の再確認で 239/240 件成功。Pod 1 の最初の IPv4 だけ `dial tcp ... i/o timeout`、
プログラム開始から 405 ms、接続 deadline は 400 ms。IPv6 初回と、その後の IPv4／IPv6 は指定 Egress IP で成功した。
各 family の最後の 5 回も成功。先行の 240/240 成功という結果はその取得時点の記録として保持し、今回も初回成功したとは記載しない。

[公式文書](https://docs.cilium.io/en/stable/network/egress-gateway/egress-gateway/#delay-for-enforcement-of-egress-policies-on-new-pods) は新規 Pod に Policy が反映されるまで遅延し得ると説明している。
ただし今回の timeout から、Policy 未反映・SYN 損失・短い期限・スケジューリングのどれかを断定することはできない。
通常 Node IP での HTTP 成功は今回観測していない。

**対応済み：** 起動直後から測る手順、成功／失敗別の集計、最後の安定状態の確認、400 ms の条件を明記した。
**次の確認：** 新規 Pod の起動時刻、Endpoint／Policy map の反映時刻、SYN と外部受信を同時取得し、初回接続の deadline を条件別に比較する。
今回は MTU 境界までの実施範囲のため、原因を確定する追加試験や設定変更は行っていない。


<a id="ti-007-mtu-9100"></a>

## 10. TI-007：Leaf Po11〜16 の MTU 9100 統一と 9000 byte 境界確認

**課題記録日：2026-09-06。次回実施する残課題。状態：Open（未適用・未試験）。**
設計の正本は [architecture の MTU 方針](architecture.md#mtu-9100-plan)。

### 10.1 目的と現状との差

Node Fabric の MTU `9100` に合わせ、他サーバ向けも含め Leaf の既存 `port-channel11`〜`16` を `9100` に統一する。
Pod と外部サーバは MTU `9000` を維持し、IP 全長 `9000` byte までの双方向到達を確認する。
2026-09-06 の修正は Leaf0103／0104 のサーバ向け Po11 を `1500` → `9216` にしたもので、
`1400`〜`8900` byte の 180 packet が成功した。`8901`〜`9000` byte は測っておらず、100 byte の減少が必要と判明したわけではない。

旧設計書は Node `9100` と Leaf／Fabric `9214`・`9216` を区別しており、Po11〜16 全体の `9100` 統一までは定めていなかった。
前回は障害区間の復旧を優先して既存 Leaf 値へ揃えたが、全サーバ向けの設計照合と `9000` byte の受入確認を完了条件へ含めなかった。
今回、設計書の範囲と次回の完了条件を明記した。TI-004 の高負荷損失、TI-005 の管理側 VXLAN は別課題として維持する。

### 10.2 次回の実施順序

1. **端末 B：変更前の棚卸し。** 各 Leaf の Po11〜16、物理メンバー、vPC 対向、接続先 Node／サーバ、SVI、`system jumbomtu`、peer-link／uplink の config と実 MTU を保存する。存在しない Po は新設しない。Node の Fabric NIC・bond・VLAN は `9100`、その他サーバは `9000` を確認する。
2. **設計・config の確定。** NX-OS の L2 MTU 制約と `system jumbomtu` 変更の波及範囲を調べ、Po11〜16 の目標 `9100` を実現する方法、Fabric 内部のカプセル化余裕、vPC 両端の投入順序、ロールバックを決める。他ポートを維持したまま変更できない場合は、その影響を明示して方針を確定する。実機確認前の一括置換は行わない。
3. **修正・適用。** singlesite の対応 config と稼働環境へ反映し、multisite は `as-equals` と正規生成した `as-changes` の config のみ更新する。公開 config のサニタイズも実施する。config と実 MTU、LACP／vPC、BGP、API、LB の変更前後を照合し、running／startup の保存状態を別々に記録する。
4. **端末 A：観測、端末 B：サイズ試験。** 試験手順に各端末の環境設定・待受・送信・期待出力・証跡保存コマンドをその場で揃えてから再実行する。端末 A で Gateway／外部サーバの capture と counter を取得し、端末 B で gw-a／gw-b／通常経路、IPv4／IPv6 の低レート比較を行う。過去の `8900` に加え IP 全長 `8999`／`9000`／`9001` byte を測る。
5. **判定・記録。** `9000` 以下は双方向に回収できることを確認し、`9001` は MTU `9000` を超える対照としてローカル送信エラー、ICMP fragmentation needed／Packet Too Big、fragmentation の有無、失敗区間を記録する。9001 の全件成功を要求せず、無応答だけで PMTUD 正常とも判定しない。低レート TCP／UDP、API／BGP／LB の回帰も確認し、実施日・コマンド・ハッシュを新しい結果として保存する。

UDP の IP 全長と payload を混同しない。IPv4 header 20 byte、IPv6 header 40 byte（追加 header なし）、UDP header 8 byte の条件では次の値になる。

| IP 全長 | IPv4 UDP payload | IPv6 UDP payload | 位置付け |
|---|---|---|---|
| 8999 | 8971 | 8951 | MTU 直前 |
| 9000 | 8972 | 8952 | 目標 MTU |
| 9001 | 8973 | 8953 | MTU 超過の対照 |

**終了条件：** 対象一覧と config・稼働値が一致し、9000 byte までのサイズ試験と低レート回帰が成功、超過時の挙動と保存状態が説明できること。
高負荷性能はこの確認後に TI-004 として継続する。TI-005 が残る経路を Fabric underlay の合格証跡に置き換えない。
kernel 更新、Node／kind worker／containerlab 再起動、停止中 multisite の起動・実機適用は本件の今回実施範囲に含めない。

参照：[Cisco の MTU 設定制約](https://www.cisco.com/c/en/us/support/docs/switches/nexus-9000-series-switches/118994-config-nexus-00.html)、
[過去の MTU 修正・再試験](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-fix-result.md)。
