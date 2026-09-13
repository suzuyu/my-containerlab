# 2026-09-12 single-site 設定照合・全体回帰・性能切り分け

## 範囲

ユーザー指定の 1〜3（設定・試験台帳の整合、connectivity 全体再試験、遅延・再送の切り分け）を
clab01 の `adc-k02` で実施する。セッションは `singlesite-regression-a34lz3g0`。
設定照合・全体回帰・性能切り分けを実施し、結果と残課題を以下へ記録する。

kernel 更新は multisite 試験後に検討する。Node の再起動は行わず、新規構築・初回適用の再現性を
multisite 構築時に確認する。BGP の計画退避、経路途中の PMTUD、SNAT port 枯渇は今回の対象外。

## 1. 設定・保存値の照合

| 照合対象 | 結果 |
|---|---|
| Leaf 4 台の Po11〜16 | 全 24 Po の MTU `9216`、LACP の member `P` を確認 |
| k02 の LACP | 全 3 Node で active aggregator の port 数 `2`、member は up |
| Node Fabric MTU | 全 3 Node の eth1／eth2／bond／VLAN、計 12 interface が `9150`。管理側 eth0 は `1500` |
| Node IP | Kubernetes InternalIP と kubelet 引数が Fabric IPv4／IPv6 に一致 |
| Cilium MTU | Helm values と Cilium ConfigMap が `9050` |
| 既存 Pod の MTU | lab-smoke の 3 Pod が interface `9050`、IPv4／IPv6 の default route MTU `9000` |
| Egress 初期化 | helper の check に成功。対象 worker 2 台の IP と checkpoint が一致 |
| CoreDNS | check-only で稼働中の forward と選定 resolver が一致。設定変更なし |
| checksum 回避策 | 両 worker の VXLAN TX checksum off と 30 秒周期 timer を確認 |
| 保存設定の配送 | topology、base values、初期化 helper／manifest、Leaf 4 台の保存 config がローカルと実行ホストで同一ハッシュ |
| Helm の明示設定 | base、observability、single-site Egress の 3 values を統合した 63 項目が稼働値と一致 |
| client tools | `prepare-tools.sh --check` で kubectl／Cilium CLI／Hubble CLI／Helm の固定 version と保存 checksum に一致 |

Hubble CLI `1.19.4` と Relay `1.20.1` の version 差は維持した。全体試験開始時の Relay 接続は 3 Node で成功。
今回の照合で追加投入を必要とする不一致は見つからなかった。Leaf の最新 MTU／LACP 変更の
startup-config 保存は既存の未実施事項として残し、今回 `write memory` は実行しない。

[build-plan](../../../build-plan.md) の旧 MTU・管理側 InternalIP・Egress 初期化方式に関する状態を更新した。
09-06 の失敗結果を含む履歴は保持する。

## 2. connectivity 全体再試験

2026-09-12 22:49〜23:51 JST（62 分 9 秒）に完走。CLI は既存の `v0.19.7-lab-flowfix.3` を SHA256 で照合し、標準 CLI を置換せず使用する。
IPv4／IPv6、strict flow validation、今回期間の agent log を対象とし、test selector による除外を追加しない。
CLI 上限は 120 分、外側は 121 分。試験前後の Cilium 設定・agent UID・BGP・drop counter を記録する。

この CLI は [ラボ用の観測基準修正版](../../../reference/cli-lab-flowfix-build.md) であり、公式版の全体合格を意味しない。
既存の累積 drop counter は消去していない。結果は **80/82 tests 成功、2 tests／3 actions 失敗**、
全 1,164 actions、50 tests skip。条件により skip した項目は合格数に含めない。

| 失敗した test | 内訳・切り分け |
|---|---|
| `node-to-node-encryption` | host → remote host の IPv4／IPv6、2 actions で期待 packet の capture なし。試験用 Pod の旧 IP を下記で再確認 |
| `no-unexpected-packet-drops` | worker の累積 `FIB lookup failed` が 48→48、`No Egress IP configured` が 12→12。今回の増加は 0 |

Cilium agent の UID／container ID／再起動回数、ConfigMap data、標準 CLI は試験前後で同一。
試験用 Policy は撤去済み。今回期間の agent log 検査は成功した。
`Invalid source ip` は全 Node 合計で 24 増えたため、全 drop が増加ゼロだったとはしない。
Policy による拒否 counter も増加しており、意図した拒否試験を含む全体値を性能上の損失率には使わない。

補助 Hubble observer は JSON 200,219 行を記録し、開始直後に control-plane の ring buffer で
1 event の欠落通知を受けた。JSON 解析エラーは 0。したがって補助 capture の完全性は保証しない。
JUnit は重複 attribute により XML として不正だったため、原本を保存し、CLI 最終集計と action ログを照合した。

### 全体試験中に判明した試験用 Pod の旧 IP

`node-to-node-encryption` の host → remote host の IPv4／IPv6 で、期待した packet を capture できない失敗が発生した。
この試験は暗号化未使用時の sanity 確認であり、暗号化機能を有効化した結果ではない。
worker の既存 `host-netns` Pod に旧管理 IP が残り、Node の Fabric InternalIP と不一致だった。
試験コードはこの Pod IP から返信側の interface／filter を選ぶため、実際の ping 宛先が Fabric でも、
返信の確認が管理側 `eth0` と旧 IP を対象としていた。ping の実行失敗は当該ログにない。

全体試験後に worker の旧 IP の試験用 Pod 1 個だけを再作成し、両 worker の Pod IP が Node InternalIP と一致した。
23:55〜23:56 JST の限定再試験で **1 test／6 actions が成功**。host 間の IPv4／IPv6 を含め capture も成功した。
Node／Cilium agent は再起動していない。試験用 Pod の旧 IP による観測対象の不一致と判断する。

初回の限定実行は selector に終端指定を付け、test／scenario 名に一致せず対象 0 件となったため結果から除外した。
`--test '^node-to-node-encryption/'` で再実行し、実施件数を確認した。
限定再試験の成功をもって、先行する全体試験を全項目合格へ書き換えない。

## 3. 遅延・再送の切り分け

全体試験と限定再試験の終了後、23:56 JST に測定を開始した。通常／gw-a／gw-b を順番に適用し、次を比較する。

- UDP payload `1200`／`8000` byte、IPv4／IPv6、目標 `0.1`／`1`／`5`／`20` Mbps。
- 各測定は 5 秒送信し、その後 5 秒まで応答を観測する。送信期間終了 + 500 ms までの回収、遅延回収、
  観測終了時点の未回収を、実行 ID と送信番号で分ける。
- 従来の UDP probe の `1` Mbps 比較と、TCP write `8000`／`262144` byte の比較も保持する。
- gw-a の小さい UDP は、同じ条件を capture 停止後にも測定し、取得処理の影響を比較する。
- Pod、Node Fabric、Leaf の端末接続側、BGR、外部サーバを同時 capture し、CPU、interface／qdisc、
  SNMP、BPF counter を照合する。
- 最初の実行では観測時間内の未回収が 5% を超える条件で上位レートを停止。再実行では遅延回収も含む 5% 超過で停止した。
  LB／API の状態悪化を認めた場合も、回復確認まで負荷増加を止める。

[UDP 診断コード](../../../../../scripts/cilium-lab/egress-latency-probe/README.md) は、遅延・重複・順序逆転の分類を
単体試験と loopback の遅延 echo で確認した。送信遅れを取り戻す burst を抑える pacing のため、
従来 probe との比較では設定 Mbps と実測 Mbps を区別する。

常用の `egress-probe` バイナリは TCP socket 情報を出力しない旧版だったため、既存の計測対応ソースから
専用バイナリを構築した。常用バイナリは置換せず、試験用 Pod／サーバでのみ使う。
loopback で TCP の全量回収と `TCP_INFO.total_retrans` の出力を確認し、実測バイナリの SHA256 を保存する。

BGR の `any` interface は Linux cooked v2 形式で、通常の `vlan` capture filter が拒否された。
試験開始前に IP／VLAN EtherType を取得する filter へ変更し、解析側で対象 probe を抽出する。
Ethernet／VLAN／IPv4／IPv6／VXLAN／Linux cooked の解析を合成 packet で確認した。
BGR の複数 interface で同一 packet が観測されることを、通信の重複とは数えない。

### 計測中断と再実行

最初の `perf-a34lz3g0` では通常 IPv4・payload 1200・目標 20 Mbps の probe が終了コード 0 で
標準出力 0 byte となった。通信結果は判定せず、原本を保存して中断した。原因は未確定。
撤去後の LB／API と初期化 check は成功し、初回はそれ以前の 3 条件だけを有効な結果として扱う。

`perf-b34lz3g0` では probe の JSON をまず Pod 内ファイルへ保存し、別 exec で回収する方式にした。
小さい UDP の 5 Mbps ですでに秒単位の遅延が生じたため、遅延回収も停止基準へ加えた。
対象 0 件の限定実行や中断した性能実行を、合格件数に加算しない。

### 測定結果

再実行は 2026-09-13 00:00〜00:16 JST に完了。主測定の UDP 40 条件、capture 停止対照 2 条件、
従来 UDP probe 12 条件、TCP 12 条件を実施した。主測定では下表のように遅延と未回収が残り、性能受入は未合格。
目標値は payload の帯域であり、IP／VXLAN header と返信を含まない。

payload 1200 byte・目標 1 Mbps の比較（実測送信量 0.995〜0.998 Mbps）：

| 経路 | IPv4 RTT p95 | IPv6 RTT p95 | 従来 cutoff 後の回収（IPv4／IPv6） | 最終未回収 |
|---|---:|---:|---|---|
| 通常 | 191 ms | 238 ms | 0／0 | 両方 0 |
| gw-a | 1,605 ms | 1,318 ms | 104/520／79/518 | 両方 0 |
| gw-b | 226 ms | 340 ms | 0／0 | 両方 0 |

通常／gw-b の payload 1200・目標 5 Mbps では RTT p95 が約 3.9〜4.3 秒となったが、追加観測で全量を回収した。
gw-a の小さい UDP は 1 Mbps で遅延回収が 5% を超えたため、5／20 Mbps を実施していない。
全経路の payload 8000・目標 5 Mbps は全量回収し、従来 cutoff 後の回収も 0 だった。

payload 8000 byte・目標 20 Mbps の比較（実測送信量 18.906〜19.443 Mbps）：

| 経路 | IPv4 送信／期限後回収／最終未回収 | IPv6 送信／期限後回収／最終未回収 |
|---|---|---|
| 通常 | 1519／334／2 | 1477／299／8 |
| gw-a | 1503／507／514 | 1509／606／695 |
| gw-b | 1484／913／7 | 1496／555／5 |

ここで「最終」はアプリの送信終了 + 5 秒。capture はその後も取得し、次のように区別できた。

- gw-a IPv4：未回収 514 のうち 504 はアプリの期限後に Pod へ到着した。残る 10 はサーバで request を
  capture したが reply がなく、同 phase のサーバ `Udp.RcvbufErrors`／`Udp.InErrors` の増加各 10 と一致した。
- gw-a IPv6：送信側 Node／Leaf0101 で request 1509、gateway Node／外部サーバで 814。
  残る 695 は後続の phase 内 capture にも現れず、送信側 Leaf から gateway 側までの Fabric 区間が未観測箇所。
  capture 自身の kernel drop は 0。ただし、どの NX-OS 内部 queue／転送処理で失われたかは未確定。
- 通常／gw-b：表の未回収計 22 は Pod capture に期限内の返信が存在した。Fabric 上の欠落とは扱わず、
  Pod 内の UDP socket 受信・アプリ回収側を次回確認する。今回 Pod netns の socket drop counter は取得していない。

診断 probe の payload 不一致・異なる実行 ID・重複 echo は主測定で 0。単なる受信 byte 数ではなく、実行 ID と
送信番号を照合した。従来 probe は pacing と 500 ms の待ち時間が異なるため、別の比較データとして保存した。

### 遅延・順序逆転の位置

通常 IPv4・payload 1200・目標 5 Mbps では、Node → Leaf、Leaf → サーバの各接続区間の p95 は
0.1 ms 未満だった。一方、Leaf0101 の端末側 tap から Leaf0103／0104 のサーバ側 tap までの p95 は
約 3.13 秒。これらは同じ Linux host の capture 時刻差であり、NX-OS 内部の ASIC／queue timestamp ではない。

同じ UDP flow の request 2405 が Leaf0103 側へ 1215、Leaf0104 側へ 1190 到着し、各 Leaf 側では
送信番号の逆転が 0 だったが、サーバで統合した受信順では 1129、Pod の返信順では 1719 の逆転を観測した。
複数の Leaf 経由での到着順序差が確認でき、MTU 境界による送信拒否とは異なる。

通常の対象 probe は BGR で観測されず、gw-a／gw-b の返信は BGR を経由した。
gw-a・小さい UDP・1 Mbps の BGR tap 入出力間 p95 は IPv4 75 ms、IPv6 50 ms。
その前後の Fabric 区間も含めると秒単位になるため、BGR 内部処理だけを原因とはしない。
BGR tap の入側は `PACKET_OUTGOING`、出側は実 capture の `PACKET_OTHERHOST` を確認して対応付けた。

capture 停止対照でも gw-a・小さい UDP・1 Mbps の p95 は IPv4 975 ms、IPv6 1,587 ms。
IPv6 は 105/520 が cutoff 後に到着し、最終未回収は両方 0。capture だけを原因とする説明には合わない。
条件ごとに 1 回の比較であり、反復統計による性能保証ではない。

### TCP と resource／queue

TCP 12 条件は全量回収、アプリ error は 0。8000 byte 単位の送信は 6 条件とも接続単位の再送 0。
256 KiB 単位では各条件 786432 byte を回収したが、`TCP_INFO.total_retrans` の増加が残った。

| 経路 | IPv4 再送 | IPv6 再送 |
|---|---:|---:|
| 通常 | 5 | 3 |
| gw-a | 30 | 2 |
| gw-b | 7 | 6 |

サーバの `TCPOFOQueue` は phase ごとに 56／78／45 増え、SACK／DSACK 関連 counter の増加も確認した。
順序逆転は再送原因の候補だが、各再送をすべて同じ原因に確定してはいない。

20 CPU の host 利用率は p50 62.5%、p95 73.7%、最大 78.6%。Leaf container の最大値は 174〜192%
（Docker 表示では 100% が論理 CPU 1 個分）。サーバは最大 9.6%。CPU quota の制限はなかった。
個別 vCPU の飽和や NX-OS 内部 queue の場所は未確認で、host 全体の CPU 枯渇と断定しない。

取得した Linux qdisc drop と host の `softnet.dropped` は増加 0。`softnet.time_squeeze` は
phase ごとに 88／97／86 増加した。これは host 共通の値で、各 container の数値を加算しない。
Node／サーバの bond の `rx_dropped` は各 phase で同程度（18／16／20）増えたため、背景 traffic を含む
interface counter だけで対象 probe の廃棄箇所を確定しない。NX-OS 内部の queue drop は別途確認が必要。

既存 `FIB lookup failed=48`／`No Egress IP configured=12` は各 phase で増加 0。
`Invalid source ip` は worker 合計で 14 増えたため、全 BPF counter が増加ゼロだったとはしない。
両 worker の管理側 `eth0` では 3 経路の対象 packet は 0。

### 最終状態と次の切り分け

測定中・撤去後の LB 確認は **232/232 HTTP 成功**、API 異常なし。42 capture の取得側 kernel drop と解析エラーは 0。
最終照合は全項目成功。Node 3 Ready、Cilium 3/3、BGP 8 Established、Node MTU／LACP／checksum timer、
初期化 DaemonSet／ConfigMap／`egress0`、CoreDNS、Cilium 設定・agent の UID／再起動回数を維持した。
一時 Egress／Network Policy・BGP 広報・試験 namespace・専用サーバは撤去済み。

TI-004 は `Open` を維持する。次の性能切り分けでは、以下を同じ低レートから比較する。

1. Leaf uplink／Spine／peer-link の capture を追加し、今回絞った Fabric 区間の遅延・欠落を hop ごとに分ける。
2. 複数 Leaf 経由の同一 flow と到着順を照合し、必要なら経路を固定した対照試験を別途計画する。
3. Pod netns の UDP socket drop とサーバ受信バッファを測定し、期限超過・socket drop・Fabric 欠落を別々に評価する。

今回の結果だけを理由に MTU や buffer を追加変更しない。kernel 比較は合意どおり multisite 試験後、
初回適用の再現性は multisite 新規構築時に確認する。

## 証跡

Git 管理外の `nxos_singlesite/operations/cilium-lab/2026-09-12/adc-k02/raw/` 配下へ保存する。
セッション `singlesite-regression-a34lz3g0` を実行ホストとローカルへ保存する。
`SHA256SUMS` に各ファイルのハッシュ、`transfer-verification.json` に両側の照合結果を保存する。
manifest 自身と転送照合記録は manifest の集計対象から除く。

証跡には事前／最終 audit、Leaf の読み取り結果、全体・限定 CLI ログ、packet capture、resource／counter、
使用した計測コード・バイナリのハッシュ、中断した計測の原本を含む。生ログを Git へ追加しない。
公開 config 検査は 122 ファイル成功、変更 0、username 残存 0。既存の使い捨て lab 用管理設定 530 行は保持した。
Git の stage／commit／push、Leaf への追加 config 投入、`write memory` は実施していない。
