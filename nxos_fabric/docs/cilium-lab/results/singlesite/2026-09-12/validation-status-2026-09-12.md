# 2026-09-12 Single-site MTU 修正と LACP 確認

**後続の全体回帰：** [設定照合・connectivity 全体回帰・性能切り分け](singlesite-regression-validation-2026-09-12.md) に最新結果を記録する。
設定照合は一致。全体は 80/82 tests 成功、50 skip。旧 IP の試験用 Pod を再作成した限定 6 actions は成功した。
累積 FIB／Egress IP 未設定 counter は今回増加していないが、全体合格とは扱わない。
性能切り分けでは Fabric の遅延・順序逆転・一部欠落と socket 側未回収を分離した。TCP 12 条件は全量回収したが再送が残る。
LB 232/232 と最終状態照合は成功し、TI-004 を継続する。

**後続の初期化方式：** [Egress interface 初期化 DaemonSet の統合試験](egress-interface-init-validation-2026-09-12.md) を完了した。
基本 HTTP 48/48、新規 Pod 240/240 が成功し、試験後も DaemonSet と両 worker の `egress0` を保持している。

**最新状態：** 後続作業で k02 の Node Fabric MTU を `9150`、Cilium の基準 MTU を `9050` へ変更した。
既存 Pod も再作成なしに interface `9050`・経路 MTU `9000` へ更新された。
さらに全 3 Node の InternalIP と Cilium 終端を Fabric 側へ変更し、gw-a の Fabric 通過と両 worker の eth0 で対象 VXLAN 0 を確認した。
通常／gw-a／gw-b × IPv4／IPv6 で Pod の ICMP／UDP 9000 byte が成功し、TI-005／TI-007 の経路・サイズ受入は完了。
Fabric 切替後の gw-a では小さい UDP が待ち時間を超過するため、TCP 再送とともに TI-004 へ残す。
詳細は末尾の [Fabric underlay 修正記録](#fabric-underlay-fix) を参照する。

以下は変更前を含む実施履歴である。Leaf0101／0102 の Po11〜15 の LACP 参加設定と MTU を復元し、5 台とも 2 ポートの集約を確認した。
初回の Po11 疎通には両 family 各 1 packet の未応答があり、再測定は各 5/5 成功。
追加の比較試験により、`8999` byte の拒否原因は Pod の経路 MTU `8950` と確認した。
Pod interface は `9000` だが、Cilium の VXLAN overhead を引いた経路 MTU が IPv4／IPv6 の ICMP／UDP に適用される。
詳細は末尾の追加実施記録を参照する。

## 結果

ユーザーの修正依頼により、Leaf0103／0104 の `port-channel12`〜`14` を MTU `1500` から `9216` へ変更した。
物理メンバー `Ethernet1/2`〜`4` の実 MTU も `9216` に追従し、全対象が up、vPC の整合性は正常だった。
`system jumbomtu` は `9216` を維持した。以前の TI-007 の `9100` 統一案は未適用であり、今回の結果をその完了とはしない。

| 対象 Po（両 Leaf） | 接続先 | 修正後の確認 |
|---|---|---|
| Po12 | `adc-t1sv0201` | Po／member が up・9216、サーバ bond は 2 ポートで LACP 集約 |
| Po13 | `adc-t2sv0102` | Po／member が up・9216、サーバ bond は 2 ポートで LACP 集約 |
| Po14 | `adc-k01-worker2` | Po／member が up・9216、Node bond は 2 ポートで LACP 集約 |

## 通信確認と限界

送信元は Po12／Po14 の比較で `adc-t1sv0102`、Po13 の比較で `adc-t2sv0101`。
各対象へ IPv4／IPv6 の ICMP Echo を送り、fragmentation を抑止した条件で応答を確認した。

- IP 全長 `1400`／`8999`／`9000` byte：3 経路 × 2 family × 3 サイズ × 3 packet、54/54 応答。
- IP 全長 `9001` byte：6 条件とも送信元で `message too long`、MTU `9000` のローカル拒否。経路途中の ICMP による PMTUD を実証した結果ではない。
- Cilium は 3/3 Ready、Node は 3 台 Ready、BGP は 8 Established、API readyz は成功。
- 既存 LB の Cluster／Local × IPv4／IPv6 × 3 回は 12/12 成功。両 worker の checksum off を維持。
- 対象サーバ／Node から開始する逆方向試験、全 LACP member の個別通過、無瞬断、Egress Policy の gw-a／gw-b 比較、低レート TCP／UDP は今回未実施。

## Leaf0101／0102 の LACP 不一致

両 Leaf の Po11〜15 はメンバーなしで down、対応する Ethernet1/1〜5 は独立した trunk として up。
保存 config にある `channel-group 11`〜`15 mode active` が稼働設定にはない。

| Po／物理ポート（両 Leaf） | topology の接続先 |
|---|---|
| Po11／Ethernet1/1 | `adc-ctsv0101` |
| Po12／Ethernet1/2 | `adc-t1sv0101` |
| Po13／Ethernet1/3 | `adc-t2sv0101` |
| Po14／Ethernet1/4 | `adc-k01-control-plane` |
| Po15／Ethernet1/5 | `adc-k01-worker` |

上のサーバ 3 台は bond mode `802.3ad` だが Partner MAC が未学習、active aggregator の port 数は 1。
2 本の NIC の aggregator ID が異なり、意図した 2 ポートの LACP 集約とは一致しない。
物理リンクの up や個別の疎通成功を LACP の冗長性確認とはしない。この事前確認時点では k01 の上記 2 Node の bond 詳細は未取得だった。
不一致の発生時期・理由は未確定。この後、末尾の追加作業で k01 も確認して復元した。
`adc-k02-worker2` 向け Po16 はこの欠落の対象ではない。

## MTU の推奨と残項目

今回の構成では Leaf の L2 jumbo を `9216`、kind k02 Node の Fabric を `9100`、Pod と通常サーバを `9000` とする構成を推奨する。
Leaf の L2 通過上限と端末の IP MTU を同値にする必要はなく、サーバを `9216` に上げる変更は行っていない。
[Cisco の MTU 設定資料](https://www.cisco.com/c/en/us/support/docs/switches/nexus-9000-series-switches/118994-config-nexus-00.html) にある
L2 の system jumbo 依存を踏まえ、既存の `9216` を維持して対象ポートの不足を修正した。
SVI／L3 MTU、カプセル化後のサイズ、管理側 VXLAN の TI-005 は引き続き別途確認する。

## 保存・証跡

single-site の 2 config、multisite の `as-equals` 2 config と正規生成した `as-changes` 2 config、計 6 ファイルへ反映し、
実行ホスト上の対応ファイルも退避後に転送・ハッシュ照合した。初期投入用の物理メンバーには `channel-group` より前に `mtu 9216` を記載する。
multisite の実機投入は行っていない。サニタイズは 122 config を検査して成功、username 残存・global address・秘密鍵の検出はなし。
既存の SNMP／NTP／logging サンプル設定は 530 行を維持し、今回変更していない。

**今回の MTU 変更の startup-config 保存は未実施。** 採取した startup の Po12〜14 とメンバーには MTU 指定がなく、running と区別する。
Node／host／kernel の再起動、Git の stage／commit／push は行っていない。

Git 管理外の証跡は `nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-09-12/adc-k02/raw/` の
`po12-14-mtu9216-before`／`apply`／`after`（後二者も同じ prefix）、`po12-14-mtu9216-traffic` に保存する。
通信ログは転送元 SHA256SUMS と照合済み。Leaf SSH の出力はローカルへ直接取得した。
前回の事前確認と未適用案は [TI-007](../../../test-issue-register.md#ti-007-mtu-9100) の履歴として保持する。

## 追加実施：Leaf0101／0102 の Po11〜15 の復元

ユーザーの「推奨で修正して状態確認」の依頼により、対向サーバ 3 台と k01 の control-plane／worker を確認した。
5 台とも `802.3ad`、eth1／eth2 が bond に参加し、修正前は Partner MAC が未学習、active aggregator は 1 ポートだった。
サーバの bond 設定・IP・MTU は維持し、両 Leaf の Po11〜15 に `mtu 9216` を設定してから、
Ethernet1/1〜5 に対応する `channel-group 11`〜`15 mode active` を復元した。

初回の Po11 はサーバが 2 ポートを認識した時点でも Leaf0102 のメンバーが down だったため、一度変更前へ戻した。
再実行では両 Leaf の収束を待ち、接続先ごとにメンバー・vPC・bond の整合を確認して次へ進んだ。
最終的に全対象 Po が `SU`、全メンバーが `P`、Po と物理 interface の MTU は `9216`、vPC の整合性は正常。
5 台とも同じ aggregator に 2 ポートが入り、Partner MAC を認識している。

| 確認範囲 | 結果 |
|---|---|
| Po11 の controller サーバ → gateway、IP 全長 1400 byte | 初回は IPv4／IPv6 とも 2/3 応答。再測定は各 5/5 応答。初回の未応答原因は未確定 |
| Po12〜15 の各接続先、IPv4／IPv6、IP 全長 1400／9000 byte | 16 条件・48/48 応答 |
| 初回疎通全体 | 52/54 応答。終了コードだけを見て行った 54/54 という途中報告は訂正済み |
| k01／k02 | API readyz 成功、各 3 Node Ready |
| Cilium／BGP／既存 LB | Cilium 正常、BGP 8 Established、LB 12/12 HTTP 成功、checksum off を維持 |

Po11 の gateway 向け jumbo、片系リンク断・復旧、全通信の無瞬断は検証していない。
Po11〜15 の MTU を single-site の 2 config へ追加し、既存の物理ポートの LACP 設定と整合させた。
multisite の対応する `as-equals` では Po と物理ポート双方へ MTU を追加し、`as-changes` を正規生成した。
この追加分も 6 config を実行ホストへ退避・転送・ハッシュ照合済み。multisite の実機投入は行っていない。
122 config のサニタイズ検査は成功。既存の管理サンプル設定 530 行を維持し、新しい認証情報は追加していない。

**LACP・MTU の startup-config 保存は未実施。** 今回の変更は running と保存ファイルへの反映であり、装置再起動後の維持を確認した結果ではない。
証跡は `raw/lacp-po11-15-leaf-before`、`lacp-po11-15-restore-v2`（戻した初回）、
`lacp-po11-15-restore-v3`（成功）、`lacp-po11-15-leaf-final`、`lacp-po11-15-traffic`、`lacp-po11-recheck` に保存した。
`lacp-po11-15-restore` は採取文字列の改行形式による事前検査停止で、config 投入前の記録である。

## 追加 Egress 試験：8999 byte の送信拒否

LACP 修正後、元の TI-007 の境界・低レート試験を再開した。試験用 namespace、Pod、capture、専用サーバ、
Egress IP と広告を準備し、Policy 未適用の通常経路から開始した。

- IPv4／IPv6 HTTP の通常送信元は期待する worker2 の Fabric IP と一致。
- 通常経路の IPv4 UDP、IP 全長 `8900` byte は 3/3 echo 成功。
- 続く `8999` byte（UDP payload `8971`）は 3 回とも `write: message too long`。送信成功数は 0。
- 対象 Pod の `eth0`、既存 lab-smoke Pod の `eth0`、Cilium ConfigMap の MTU 値はいずれも `9000`。
  単純に Pod interface が 8950 だったという説明は成立しない。
- 同時取得した Node／サーバ capture に MTU を通知する ICMP は確認できず、取得側の kernel drop は 0。
  既存 lab-smoke Pod の route 表示にも明示 MTU は見えなかった。失敗した socket の有効 MTU・経路と送信拒否箇所は未特定。
- この失敗で試験を中断。IPv6 UDP の境界、gw-a／gw-b、低レート TCP／UDP は未実施。
- 試験用 Policy 名の後片付け、広告、Egress IP、namespace、専用サーバの撤去は成功。
  終了時の Cilium・BGP・API・既存 LB を再確認した。Cilium 設定・Node MTU・kernel は変更していない。

これはサーバ起点の ICMP 9000 byte 成功とは別の条件であり、LACP 復元や Leaf MTU の失敗と同一視しない。
TI-007 の Egress 9000 byte 受入は未完了とする。
証跡は `raw/egress-mtu-resume`、`egress-pod-mtu-check`、`egress-pod-route-check`。失敗条件と cleanup 結果を保持する。

## 追加比較：同一 Pod の ICMP／UDP／TCP と経路 MTU

ユーザーの追加依頼により、同じ `selected` Pod（`adc-k02-worker2`）から同じサーバ `adc-t1sv0102` へ、
通常経路、gw-a、gw-b を順番に測定した。ICMP と UDP は fragmentation を抑止し、TCP は MSS を強制せずに測定した。
UDP／TCP は従来の `client` container、ICMP と経路表示は同一 Pod の診断用 sidecar を使い、network namespace を共有した。
HTTP で各条件の送信元が通常の worker2／gw-a／gw-b の期待 IP と一致することを確認した。

### 8999 byte の拒否原因

- Pod の `eth0` は MTU `9000`。一方、IPv4／IPv6 のデフォルト経路に `mtu 8950` が明示されていた。
- connected UDP socket の `IP_MTU`／`IPV6_MTU` も送信前から `8950`。`8951` 以上の書き込みは 0 byte、`message too long` で拒否された。
- Cilium の実設定は `mtu=9000`、`routing-mode=tunnel`、`tunnel-protocol=vxlan`。
  [Cilium 1.20.1 の MTU 計算](https://github.com/cilium/cilium/blob/v1.20.1/pkg/mtu/mtu.go) は、
  device MTU と route MTU を分け、IPv4 underlay の tunnel overhead `50` byte を route MTU から差し引く。
  実測した `9000 − 50 = 8950` はこの動作と一致する。
- 通常経路の IPv4／IPv6、`8900`／`8999` byte を従来バイナリでも再測定し、診断版と成功／拒否が一致した。
- 前回の簡易的な `ip route` 表示で明示 MTU が見えなかったことを、MTU 指定が存在しない根拠にはできなかった。
  今回は iproute2 の詳細表示、宛先ごとの route lookup、socket の値を照合した。

| IP 全長 | ICMP：通常／gw-a／gw-b、IPv4／IPv6 | UDP：同じ 6 条件 |
|---|---|---|
| 8900／8949／8950 byte | 各サイズ・各条件で 3/3 応答 | 各サイズ・各条件で 3/3 echo 成功 |
| 8951／8999／9000／9001 byte | ローカルの MTU エラー、送信先からの応答なし | 各条件 3 回とも write 拒否、送信成功 0 |

成功側は ICMP と UDP それぞれ 54/54 応答。ICMP の拒否条件は各 1 回のローカルエラーで終了しており、
指定した `-c 3` を実際の送信数として集計していない。
この結果は経路途中の ICMP による PMTUD の実証ではなく、Pod に設定された経路 MTU によるローカル制限の確認である。

### TCP の結果と残る再送

TCP は 1 stream、1 Mbps 設定、5 秒指定、1 回の write を `256 KiB` として測定した。
各条件で `786432` byte を送受信し、データ照合エラーは 0。
大きな write は TCP が分割して送るため、ICMP／UDP の単一 IP packet のサイズと区別する。

| 経路 | IPv4 の送受信 byte | IPv6 の送受信 byte | クライアント側 TCP 再送：IPv4／IPv6 |
|---|---|---|---|
| 通常 | 786432／786432 | 786432／786432 | 5／9 |
| gw-a | 786432／786432 | 786432／786432 | 0／0 |
| gw-b | 786432／786432 | 786432／786432 | 8／8 |

socket の PMTU は開始・終了とも `8950`、送信 MSS は IPv4 `8898`、IPv6 `8878` だった。
1 Mbps の指定は write 間隔による平均的な制限であり、`256 KiB` を一括で渡す際のバーストを抑えるものではない。
再送箇所・queue drop・並べ替えの原因は未確定で、TI-004 の性能評価は継続する。

### 低レートの追加比較

同じ Pod・宛先・3 経路・両 family で、TCP の write 単位 `8000` byte、
UDP payload `1200`／`8000` byte を各 1 stream、1 Mbps、5 秒指定で測定した。
18 条件とも送受信量が一致し、プログラムのエラーは 0。
TCP の送受信量は各 `600000`〜`624000` byte、クライアント側再送は全 6 条件で 0。
UDP は payload `1200` が各 `625200` byte、payload `8000` が各 `632000` byte だった。
これは今回の低レート・短時間の結果であり、以前の高レート損失や TCP バースト時の再送原因を解消した判定ではない。

### Node 間 VXLAN の残課題

gw-a の低レート測定と同時に worker2 の `eth0` を capture し、
`172.18.0.6 ↔ 172.18.0.2` の VXLAN と、外側 IPv4 の fragment を確認した。
管理側の MTU `1500` を通る TI-005 の設計差分が残っている。
今回の jumbo の到達成功を、Node 間で断片化なしに jumbo を通せた結果とはしない。

次は、Node InternalIP／Cilium の tunnel endpoint と Fabric 経路を整合させたうえで、
Cilium の基準 MTU・Pod の経路 MTU・VXLAN overhead を合わせる設計を確定する。
Leaf `9216`／Node Fabric `9100`／通常サーバ `9000` という値に加え、Pod の interface と route を別々に確認する必要がある。
Cilium の値だけを増やす変更や Pod の経路 MTU の手動上書きは今回行っていない。
TI-007 の Pod 起点 `9000` byte 受入は未完了とする。

### 撤去・回帰確認・証跡

- 試験用 namespace／Pod、Egress Policy、広告、両 worker の `egress0` を撤去し、専用 echo サーバを停止した。
  namespace／Policy／試験広告／Egress interface の不在と `19090`〜`19093` の待受終了を確認した。
- 終了時は Cilium `3/3` Ready、BGP `8` Established、API readyz 成功。
  Cilium agent の UID・再起動回数・Ready は試験前後で一致した。
- 既存 LB の Cluster／Local × IPv4／IPv6 は、準備の再実行分を含む各確認で合計 `36/36` HTTP 200。
  両 worker の既存 checksum off を維持した。
- Leaf・Node・Cilium の恒久設定、startup-config、kernel は今回変更していない。
- 診断版 `egress-probe.go` へ socket の経路 MTU・PMTU 設定と TCP_INFO の読み取りを追加した。
  Go `1.27.1`、Linux amd64、CGO 無効でビルドし、同じ条件の `go vet` と実環境比較を通した。
  実行ホストの従来 runtime バイナリは置換せず、一時パスの診断版を使用した。
- Git 管理外の `raw/mtu-protocol-diag/` に、コマンド、実行スクリプト、ソース、バイナリのハッシュ、経路、
  socket 診断、capture、撤去後の状態を保存した。転送元の SHA256SUMS にある `551` ファイルをローカルで照合した。
  3 経路 × 4 箇所の比較 capture と追加 underlay capture は、いずれも capture 側の kernel drop 0。
  比較 capture には ICMP fragmentation needed／Packet Too Big を観測していない。
- 初回準備は kubectl の複数 JSON 出力の解析でリソース投入前に停止した。読み取りを修正して再実行し、停止記録も保存した。
  通信の失敗として集計していない。Git の stage／commit／push は行っていない。

## Node Fabric MTU 9100 の再照合と architecture 更新

ユーザーの Node MTU 修正依頼に先立ち、k02 の control-plane／worker／worker2 を改めて照合した。
全 3 Node の `eth1`／`eth2`／`bond0` と各 Fabric VLAN、計 12 interface はすべて `9100` だった。
実行ホストとリポジトリの single-site topology も全 3 Node に `MTU="9100"` を渡しており、追加投入を要する不足はなかった。
全 3 Node の bond は 2 ポートで集約、Node は 3 台 Ready、BGP は 8 Established、API readyz は成功した。
今回の照合では稼働設定を変更していない。

[architecture の MTU 方針](../../../architecture.md#mtu-9100-plan) は Leaf の旧 `9100` 統一案を `9216` 維持へ更新し、
修正した Po／LACP と保存状態を反映した。Node Fabric の `9100` 適用済みを明記するとともに、
管理側 `eth0` の `1500`、Cilium 基準値／Pod interface の `9000`、Pod の経路 MTU `8950` を分けて記載した。
multisite topology でも k02／k03 の Node Fabric は `9100` 指定済み。k03 の稼働確認・変更は行っていない。

証跡は `raw/node-fabric-mtu9100-audit/`。転送元 SHA256SUMS の `37` ファイルを照合済み。
Node Fabric の `9100` 指定の有無と、TI-005 の underlay 選択・TI-007 の Pod 経路 MTU の残課題を区別する。


<a id="mtu9150-implementation"></a>

## Node 9150／Cilium 9050 の実装と再試験

ユーザーの依頼により、Node Fabric の容量を先に確保する方針を採用した。
現在の IPv4 VXLAN・暗号化なしで Pod の経路 MTU を 9000 とするため、
Node の設定値を `9150`、Cilium の基準値を `9050` として別々に適用した。

### 設定変更と保存状態

- k02 の control-plane／worker／worker2 の `eth1`／`eth2`／`bond0`／Fabric VLAN、計 12 interface を `9100` → `9150` に変更した。
  Node／host の再起動や Containerlab の再 deploy は行っていない。管理側 `eth0` は `1500` を維持した。
- Cilium は既存 Helm release の user values を保持し、`MTU=9050` のみを変更した。
  server dry-run の manifest 差分は `cilium-config.data.mtu` と Cilium／Operator の ConfigMap checksum annotation のみ。
  Cilium／Operator をローリング更新し、Helm の適用後 values が変更前に MTU だけを置き換えた内容と一致することを確認した。
- 既存 lab-smoke の 3 Pod は UID を維持し、interface MTU `9000` → `9050`、
  IPv4／IPv6 デフォルト経路の MTU `8950` → `9000` に更新された。
- ローカルの single-site／multisite topology の Cilium 用 Node を `9150` に更新し、
  single-site k02、multisite k02／k03 の `00-base.yaml` を `MTU: 9050` に更新した。
  3 README、architecture、パラメータ台帳も同じ設計値へ合わせた。
- 実行ホストは既存の 2 topology と single-site k02 の base values を退避して更新した。
  multisite topology はローカルと既存差分があり、Node MTU が `9000` のままだったため、
  Cilium 用 Node の MTU だけを `9150` へ変更し、その他の差分を維持した。
  multisite k02／k03 の base values は実行ホストに未配置のため、ローカルの保存設定だけを更新した。
  multisite の実機投入は行っていない。
- Leaf の `9216`、通常サーバの `9000`、既存 checksum 回避策は維持する。
  WireGuard、WAN MTU、Node InternalIP／tunnel endpoint の変更は今回行っていない。

### Node Fabric の試験

Node の network namespace を共有する一時 hostNetwork Pod から、3 Node 間の全 6 方向で試験した。
IPv4／IPv6、IP 全長 `9000`／`9150` byte は各 3/3、計 72/72 応答。
`9151` byte は 12 条件とも応答なしで、MTU `9150` のローカル拒否を対照として記録した。
試験用 namespace は撤去した。Node 内に ping がないため開始できなかった最初のコマンドも保存している。

### Pod の境界・TCP・低レート試験

worker2 の同一 Pod から `adc-t1sv0102` へ、通常／gw-a／gw-b × IPv4／IPv6 を比較した。
各経路の送信元は HTTP で期待する Node／Egress IP と一致した。新規試験 Pod の interface は `9050`、
デフォルト経路と UDP／TCP socket の MTU は `9000`。既存 3 Pod の経路 MTU とも一致する。

| IP 全長 | ICMP：3 経路 × IPv4／IPv6 | UDP：同じ 6 条件 |
|---|---|---|
| 8900／8950／8999／9000 byte | 各サイズ・各条件で 3/3 応答 | 各サイズ・各条件で 3/3 echo 成功 |
| 9001 byte | 各条件 1 回のローカル MTU エラー | 各条件 3 回とも write 拒否、送信成功 0 |

成功側は ICMP と UDP それぞれ 72/72 応答。9001 byte は socket／経路 MTU 9000 のローカル制限であり、
経路途中の ICMP による PMTUD の実証ではない。

TCP は 1 stream、1 Mbps 設定、5 秒指定、write 単位 256 KiB で測定した。
全 6 条件で 786432 byte を送受信し、照合エラー 0。送信 MSS は IPv4 8948、IPv6 8928 だった。

| 経路 | クライアント側 TCP 再送：IPv4／IPv6 |
|---|---|
| 通常 | 7／3 |
| gw-a | 0／1 |
| gw-b | 3／14 |

TCP の大きな write は複数 packet に分割されるため、単一 IP packet 9000 byte の試験とは区別する。
1 Mbps は write 間隔による制限であり、一括書き込み時のバーストは残る。

低レート比較は write 単位 8000 byte の TCP、payload 1200／8000 byte の UDP、
IP 全長 9000 byte の UDP（payload は IPv4 8972／IPv6 8952 byte）を、同じ 1 stream／1 Mbps／5 秒指定で測定した。
全 24 条件で送受信量一致・プログラムエラー 0。小分け TCP は全 6 条件でクライアント側再送 0。
今回の短時間・低レートの成功を、高負荷性能の解決とはしない。

### 残課題と撤去後の状態

- TI-007 は k02 の 9000 byte 境界・低レート受入に合格し、Resolved とした。
- TI-004 は継続。256 KiB の TCP write で再送が残り、以前の高レート損失の原因も未確定。
- TI-005 は継続。gw-a の低レート測定時にも、管理側 `eth0` の Node 間 VXLAN と外側 IPv4 の fragment を観測した。
  Node Fabric 9150 の試験成功と、Cilium が Fabric を underlay に使用することは別の確認事項である。
- 試験用 namespace／Pod／Egress Policy／BGP 広告／両 worker の `egress0` を撤去し、
  専用 echo サーバを停止した。対象リソースと 19090〜19093 の待受の不在を確認した。
- 最終状態は Helm revision 4・deployed、Cilium 3/3 Ready、3 Node Ready、BGP 8 Established、API readyz 成功。
  既存 LB の Cluster／Local × IPv4／IPv6 は適用・試験中の各確認を合わせて 48/48 HTTP 200。
  両 worker の既存 checksum off を維持した。無瞬断や再起動後の維持を検証した結果ではない。

### 証跡と検査

- Git 管理外の `raw/mtu9150-implementation/` に適用前後の設定、Helm dry-run、Node／既存 Pod の MTU、
  Node Fabric 試験と保存設定の退避を収録。転送元 SHA256SUMS の 387 ファイルを照合した。
- `raw/mtu9150-protocol-test/` にコマンド、実行スクリプト、socket 診断、capture、境界／低レート結果、撤去確認を収録。
  転送元 SHA256SUMS の 491 ファイルを照合し、全結果を機械的に再集計した。
- 比較 capture と追加 underlay capture は取得側の kernel drop 0。
  最初の通常経路測定では追加した 9050 byte 条件が probe の payload 上限により停止したため、
  その capture を `normal-first-instrument-limit/` に保存し、9001 byte までの計画で通常経路を全件再測定した。
  計測器の上限による停止と重複測定は上記の受入集計へ含めていない。
- topology と base values の YAML を読み取り、変更が対象 Node の MTU と Cilium の MTU に限定されることを確認した。
  config サニタイズは 122 ファイルで成功し、変更 0、username 行 0、既存管理サンプル設定 530 行を維持した。
  Git の stage／commit／push は行っていない。

<a id="fabric-underlay-fix"></a>

## Cilium の Node 間転送を Fabric へ修正

ユーザーの依頼により、gw-a への Node 間転送も Fabric 側だけを通す設計へ実装を合わせた。
変更前は 3 Node の kubelet 引数と Kubernetes／CiliumNode の InternalIP が管理側 IP だった。
保存 topology は Fabric IP と `configure-kubelet-node-ip.sh` の実行を指定済みであり、稼働状態との不一致を確認した。

| Node | 変更前の IPv4 InternalIP | 変更後の Fabric IPv4／IPv6 | Fabric interface |
|---|---|---|---|
| control-plane | `172.18.0.3` | `172.16.4.11`／`fd21:0:0:4::1:1` | `bond0.14` |
| worker（gw-a） | `172.18.0.2` | `172.16.4.21`／`fd21:0:0:4::2:1` | `bond0.14` |
| worker2（gw-b） | `172.18.0.6` | `172.16.4.22`／`fd21:0:0:4::2:2` | `bond0.104` |

### 適用方法

- 既存の `configure-kubelet-node-ip.sh` で kubelet の `--node-ip` を Fabric の両 family へ変更し、kubelet を再起動した。
  Node IP 更新だけでは起動済み Cilium の管理側アドレスが残ったため、該当 Node の Cilium Pod を 1 台ずつ再作成した。
- API の管理側接続先、管理側 default route、Cilium の `devices`、Helm の MTU 値は維持する。
  Node／host の再起動と Containerlab の再 deploy は行っていない。
- 最初の worker2 確認は IPv6 の省略表記を文字列比較したため正常な登録を認識できず、確認処理が timeout した。
  IP アドレスを正規化して再確認し、Node の Ready と Fabric IP の登録を確認した。通信障害としては集計しない。
- 3 Node とも Kubernetes／CiliumNode の InternalIP と Cilium の Node 一覧が Fabric IP に揃った。
  Cilium 再起動直後の health 未収束表示は、その後の全 3 agent で `3/3 reachable` に回復した。
  各 Node の IPv4／IPv6 host と health endpoint の ICMP／HTTP はすべて OK。

### 経路・サイズ試験と遅延の切り分け

worker2 の同一 Pod から外部サーバへ、通常／gw-a／gw-b × IPv4／IPv6 を比較した。
IP 全長 9000 byte は ICMP／UDP とも全 6 条件で各 3/3 応答。9001 byte は Pod の経路 MTU 9000 によるローカル拒否だった。
gw-a では次の往復経路を capture し、Pod IP packet 9000 byte を収容した外側 IPv4 VXLAN の IP 全長 9050 byte を確認した。

```text
Pod on worker2
  → bond0.104 / 172.16.4.22
  → Leaf Fabric（Cilium VXLAN UDP 8472）
  → bond0.14 / 172.16.4.21（gw-a）
  → Egress IP 172.16.24.1 または fd21:0:0:24::1 で外部サーバへ
```

初回 gw-a の小さいサイズで以下の測定上の未回収が出たため、元の結果を残して時刻と経路を照合した。

- IPv6 UDP 8900 byte：プログラムは 3 送信／2 回収。Pod capture では 3 応答が戻っていた。
  最後の往復は約 675 ms で、プログラムの 650 ms の待ち時間を超過した。
- IPv4 ICMP 8999 byte：ping は 4 送信／3 回収。capture では終了後の seq 4 も含めて 4 応答を確認した。
- gw-a の再測定で IPv6 UDP 8900 byte は 3/3 と 5/5、IPv4／IPv6 UDP 9000 byte は各 5/5。
  ICMP 8999 byte を 1 秒間隔で送った追加確認は 10/10 応答した。
- 初回の追加測定は probe の 5 回という上限を超えて停止した。上限に合わせて再実行し、停止時の capture は
  `recheck-instrument-limit/` に分けて保持した。計測器の上限による停止を通信失敗には含めない。

### 小さい UDP の送信頻度と残る性能課題

gw-a の UDP payload 1200 byte・1 Mbps・5 秒指定では、アプリケーションの送受信量が一致しなかった。
capture を終了後まで照合すると、両 family とも 521 要求／521 応答を確認した。
IPv4 の ICMP エラーに引用された UDP header は、応答数へ二重計上していない。

| family | 送信 packet | 終了時点の回収 packet | 終了後に観測した応答 | 最後の応答到着 |
|---|---|---|---|---|
| IPv4 | 521 | 317 | 204 | 終了の約 1.11 秒後 |
| IPv6 | 521 | 420 | 101 | 終了の約 1.50 秒後 |

このプログラムは指定した送信期間の終了から 500 ms 後まで応答を待つ。
今回の capture は待ち時間を超える遅延を示すため、未回収率をそのままネットワークの破棄率とは扱わない。
遅延が生じる装置・queue の確定や、高負荷性能の受入は TI-004 として継続する。
gw-a の payload 8000 byte／IP 全長 9000 byte の UDP は、両 family とも全量を回収した。

TCP write 単位 256 KiB の比較は全 6 条件で 786432 byte を送受信し、照合エラー 0。
クライアント側再送は通常 IPv4／IPv6 が 7／4、gw-a が 11／12、gw-b が 4／8 であり、再送原因の評価も TI-004 に残す。

### Fabric 経路の受入

- 3 経路それぞれ 100 秒の同時観測で、両 worker の管理側 `eth0` は VXLAN／外側 IPv4 fragment の対象 packet が 0。
- 両 worker の `bond0.14`／`bond0.104` では Fabric IP を送受信元とする Cilium VXLAN を観測し、外側 IPv4 の fragment は 0。
  gw-a の試験通信もこの経路を通った。全 12 本の interface 別 capture は kernel drop 0。
- この受入は管理側への VXLAN 流出と MTU の経路整合を対象とする。小さい UDP の期限超過や TCP 再送の解決を意味しない。

低レート 24 条件のうち、gw-a の UDP payload 1200 byte の 2 条件は上記の期限超過、残る 22 条件は送受信量が一致した。
小分け TCP の再送は全 6 条件で 0。gw-a の payload 1200 byte を 0.1 Mbps に下げた追加比較は、両 family とも 63600 byte を送受信した。

### 撤去・最終照合・証跡

- 試験用 namespace／Pod、Egress Policy、BGP 広告、両 worker の `egress0` を撤去し、専用 echo サーバを停止した。
  対象リソースと 19090〜19093 の待受の不在を確認した。
- 最終状態は Cilium 3/3 Ready、Node 3 台 Ready、全 3 agent の cluster health が 3/3 reachable、BGP 8 Established、API readyz 成功。
  既存 LB の Cluster／Local × IPv4／IPv6 は適用・試験中の各確認を合わせて 60/60 HTTP 200。
- Node Fabric の 12 interface は 9150、管理側 eth0 は 1500、Cilium 基準 MTU は 9050 を維持した。
  既存 lab-smoke の 3 Pod は UID を維持し、interface 9050／IPv4・IPv6 の経路 MTU 9000 を確認した。
  両 worker の checksum off、管理側 default route も維持した。
- Cilium ConfigMap の data と DaemonSet の spec は変更前後で一致した。Helm values の変更は行っていない。
  topology と既存 Node IP 設定スクリプトは設計どおりだったため、追加の値変更をせず稼働 Node へ適用した。
  変更した kubelet 引数は各 Node の設定ファイルに保存したが、Node／host 再起動後の維持や無瞬断の検証は行っていない。
- `raw/fabric-underlay-fix/` の 796 ファイル、`raw/fabric-underlay-test/` の 529 ファイルを転送元 SHA256SUMS で照合した。
  初回の待ち時間超過、追加測定、低レートの終了後到着を含めて結果を機械的に再集計した。
  元の結果は上書きせず保持し、Git の stage／commit／push は行っていない。

TI-005 は k02 の Fabric 経路の受入を完了して Resolved とする。遅延する装置・queue の特定と TCP 再送は TI-004 で継続する。
