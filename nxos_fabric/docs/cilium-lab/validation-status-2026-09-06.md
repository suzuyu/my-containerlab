# 2026-09-06 Single-site `adc-k02` 検証ステータス

## 1. 結論・記録の範囲

**Egress Gateway の基本機能と Leaf MTU 修正後のサイズ境界は確認済み。ただし、single-site 全体の検証完了・全項目合格ではない。**
全体 connectivity test、高負荷時の損失、Fabric 経路設計との不一致、BGP の冗長性判定を残す。
IPv6 Cluster LoadBalancer は checksum 回避策を適用した条件で成功しており、kernel の恒久修正は未実施である。

この文書は [2026-08-30 のスナップショット](validation-status-2026-08-30.md) を引き継ぎ、
2026-09-05 の Tetragon／connectivity と、2026-09-06 の CLI 修正・Egress・checksum・MTU 試験をまとめる。
ユーザー指定により、JST で 2026-09-07 未明に実施した MTU 切り分け・修正・再試験も **2026-09-06 の試験記録**に含めた。
最終 MTU 修正セッションの実時刻は 2026-09-07 01:05:14〜01:25:04 JST。生ログの日時は変更していない。
本書の整理は 2026-09-07 に行い、その際のオフライン検査を新たな実機試験とは数えない。

| 項目 | 検証環境・条件 |
|---|---|
| 対象 | `nxos_singlesite`／`adc-k02`、context `kind-adc-k02` |
| Kubernetes／Cilium／Tetragon | `v1.35.5`／`v1.20.1`／`v1.7.0` |
| host kernel | `5.14.0-611.27.1.el9_7.x86_64`。kind Node と共有 |
| Datapath | dual-stack、VXLAN、kube-proxy replacement、BPF masquerade |
| 実測 underlay | Node InternalIP と Node 間 VXLAN は管理側 `eth0`。Fabric 側を使う設計とは不一致 |
| Egress の外向き経路 | Gateway から Fabric の `bond0.14`／`bond0.104` を使用 |
| CLI | 全体試験は `v0.19.7-lab-flowfix.1`、後続限定試験は `.3`。いずれも lab 用で公式修正版ではない |
| 今回の除外 | kernel 更新、kind worker／host／containerlab の停止・再起動、Node 障害・復旧 |
| multisite | 停止中。保存 config／manifest の静的確認のみ。実機投入・Cluster Mesh／DCI 受入は未実施 |

接続先・配置パス・実施セッションの詳細は [実際の試験環境](execution-environment-singlesite-k02.md)、
再実行は [build-plan](build-plan.md) と各試験手順を正本とする。

## 2. Stage ごとの判定

| 範囲 | 2026-09-06 分までの判定 | 完了としない範囲 |
|---|---|---|
| Stage 0 host／kind | 初期 preflight の条件付き合格を継承 | 長期容量評価、multisite 同時稼働、全経路の MTU／PMTUD |
| Stage 1 Cilium 基盤 | 基本通信・限定回帰は成功 | 全体 connectivity は未合格、InternalIP 設計不一致、API 経路切替 |
| Stage 2A LB／BGP | 基本機能成功。IPv6 Cluster LB は checksum 回避策付き | `TI-002` の Forwarding／ECMP、未割当 VIP、計画退避・障害・広告収束 |
| Stage 2B Egress | 選択・SNAT・除外・異常設定時の拒否・計画切替・撤去・修正後サイズ境界を確認 | 高負荷性能、SNAT port 枯渇、Node 障害系、全体受入 |
| Stage 3 Hubble／Network Policy | `NP-00`〜`NP-07` の 2026-08-30 合格を継承。後続 CLI の選定した許可・拒否と flow も成功 | 今回全 NP を再実行したわけではない。UI の接続経路、追加 resource 評価などは別確認 |
| Stage 4 Tetragon | `TG-00`〜`TG-08` の定義した観測範囲は合格 | enforcement、accept 観測、長期負荷、停止中の IPv6 保証。一部原本の完全性照合にも制約 |
| Stage 5／6 | 設計・ファイル作成まで | multisite、Cluster Mesh、Egress 併用・DCI の実測 |

## 3. 試験結果と解釈

### 3.1 Cilium connectivity と検証用 CLI

全体試験は **54 分 49 秒で完走し、不合格**だった。実際の上限は CLI が 120 分、外側が 121 分であり、
当初の「90 分上限」の相談や前回の 30 分 timeout と区別する。
82 tests／1,164 actions のうち 78 tests／1,152 actions が成功、4 tests／12 actions が失敗。
別の 50 tests は実行条件により skip され、合格数には含めない。

| 失敗項目 | 判明した内容・後続対応 |
|---|---|
| 管理側 HostPort：6 actions | CLI が管理側 InternalIP を宛先に選ぶ一方、公開対象は Fabric 側。Fabric IP 宛ての両方向・両 family は成功。管理側への公開拡大はしていない |
| 自己宛 Service：2 actions | curl 成功と、CLI が要求する DNS／VIP 宛て packet flow の条件が一致しない。lab CLI `.3` で対象を限定した PRE socket event と curl を照合 |
| FQDN HTTP：3 actions | DNS proxy＋L3/L4 許可 Policy に HTTP access-log event を要求していた。lab CLI で Policy に対応する DNS／TCP／drop 判定へ修正 |
| unexpected drops：1 action | `FIB lookup failed=48` の累積値を検出。全体試験中の増分は 0。過去 48 件の原因確定とは扱わない |

後続 `.3` の限定・回帰は **114 actions 成功**。Service／NodePort、自己宛 Service、FQDN、拒否、HTTP L7 の条件を確認した。
この結果で全体試験の失敗を上書きしない。最新 CLI＋checksum 回避策＋MTU 修正後の全体再試験は未実施。
全体試験時に増加した `Invalid source ip` も、特定 action との関係は未確定である。

修正版は標準 CLI を置換しておらず、公式 Agent の修正でもない。
PRE は Service の socket lookup の証拠であり、変換後 backend や TCP handshake の直接証拠ではない。
6 秒待機による event 抑制対策にも負荷依存の限界がある。
[パッチ・由来・再ビルド手順](cli-lab-flowfix-build.md) に判定変更の範囲を記載した。

### 3.2 Tetragon：観測・負荷・停止安全性

Tetragon は **observe-only** として使用した。`TG-05` の拒否は既存の権限制約で発生し、Tetragon が遮断した結果ではない。

| Test ID | 確認した内容 |
|---|---|
| `TG-00` | built-in `process_exec`／`process_exit`、Pod metadata とプロセスの対応 |
| `TG-01` | custom `process_tracepoint` と namespace の対象／非対象比較。syscall list 用の型を `syscall64`、当該 kernel の format に合わせて index を `5` に修正 |
| `TG-02`／`TG-03` | 対象ファイルの write／read と対象外 path の抑制 |
| `TG-04` | HTTP 通信、`tcp_connect`／`tcp_close`、Hubble とサーバ access log の対応。初回の HTTP 未起動を修正して再試験 |
| `TG-05` | `chown` の権限エラーと capability event の対応 |
| `TG-06` | 残存 `getevents` 整理後、1 観測接続・50 回の短時間負荷に成功。負荷・回復区間の notify overflow 増分 0、Pod UID 不変・再起動 0 |
| `TG-07` | Tetragon 停止・復旧期間の既存 IPv4 通信と、復旧後の観測再開 |
| `TG-08` | 試験 Policy・待受・専用 HTTP サーバの後片付け、built-in 観測と通信の継続 |

機能判定と証跡の完全性は別管理とする。`TG-01` の対象側は提示された jq 出力が根拠で、完全な原本 JSON の照合ではない。
`TG-02`〜`TG-05` などにも転送元ハッシュ未照合の部分が残る。`TG-06` 診断 89 ファイルと `TG-08` 最終対象は照合済み。
長期メモリ安定性、無瞬断保証、個々の残存 listener 内部で停止しなかった理由は確定していない。
詳細は [Network Policy／Tetragon 手順](network-policy-and-tetragon-test-plan.md) と Git 管理外の各 `tg*-result.md` に分離した。

### 3.3 Egress Gateway の設計・基本機能・異常系

Egress IP は Node NIC と別レンジとし、各 Node の dummy `egress0` に `/32`／`/128` で保持する。
Cilium は `Interface` advertisement で個別経路を広報し、NX-OS の BGP 終端で集約も生成する。

| Cluster | 予約範囲 | Gateway A／B | 実施状態 |
|---|---|---|---|
| k02 | `172.16.24.0/24`、`fd21:0:0:24::/64` | `.1`／`.2`、`::1`／`::2` | single-site の適用・広報・通信・撤去を確認 |
| k03 | `172.16.25.0/24`、`fd21:0:0:25::/64` | `.1`／`.2`、`::1`／`::2` | 予約・静的確認のみ |

- selected の対象 CIDR 宛てだけを SNAT し、unselected・明示除外・CIDR 外は通常 Node IP を維持した。
- CIDR 外の比較は 48 HTTP 成功。外部 access log の ID・送信元とも一致した。
- Gateway selector 不一致は drop reason `194 / NO_EGRESS_GATEWAY`、利用不能 IP は `204 / DROP_NO_EGRESS_IP`。
  比較・復旧・LB を含む 88 成功と、期待する 12 拒否、計 100 接続が期待どおりだった。
- 新規 Pod 試験は先行 240/240 成功。手順再現時は 239/240 成功で、最初の IPv4 timeout 1 件を `TI-006` に記録した。
  成功通信で想定外の送信元は観測しなかったが、任意の起動条件で漏れない保証とはしない。
- `gw-a` → `gw-b` の明示切替では既存 TCP が両 family とも reset し、新規接続は切替先 IP で成功した。
  自動 HA や既存 NAT 状態の引継ぎが成功した試験ではない。
- BPF map、Node capture、BGR／Leaf の経路と counter を照合し、管理側 VXLAN → Gateway → Fabric NIC という実経路を確認した。

再実行用の構成図・端末 A／B のコマンド・出力例は [Egress Gateway 試験手順](egress-gateway-test-plan.md) に記載する。

### 3.4 IPv6 checksum の回避策

Node 間 IPv6 Cluster LB の受信 checksum 不正は、両 worker の `cilium_vxlan` で
`tx-checksum-ip-generic=off` にすると改善し、on に戻すと再現した。
helper 単体では対照 flags `0`／`16` が成功、IPv6 flag を含む `144` が `-EINVAL` だった。
旧 helper 処理と offload の相互作用が最有力だが、内部 packet 状態の全追跡や恒久修正コードの実証は未実施。

- 回避策適用後の Service／NodePort 等 114 actions、Egress 46 HTTP、LB 42 HTTP が成功。
- 登録した cluster／kernel／image／設定が一致する場合だけ、user systemd timer が設定ずれを修復する。
- worker の Cilium Pod を 1 台ずつ再作成し、約 17 秒で Ready。再作成中 208 HTTP、復旧後 84 HTTP が成功。
  interface と off 設定は維持され、監視は新しい Pod UID を認識した。この試験では再書込みは不要だった。
- Node／host の実再起動後の再適用は未確認。timer は再適用までの通信を遮断する仕組みではない。
- kernel 候補はソースを評価しただけで、更新していない。回避策を恒久修正扱いにしない。

意味・採用条件・維持／解除方法は [checksum 運用手順](checksum-compat-operations.md)、
候補の評価は [kernel 対応方針](kernel-compatibility-policy.md) と [候補評価](kernel-checksum-candidates.md) を参照する。

### 3.5 Leaf MTU 修正と再試験

サーバ `adc-t1sv0102` に接続する Leaf0103／0104 の `port-channel11` と member `Ethernet1/1` が MTU 1500 だった。
Node 向けは 9216、Node Fabric は 9100、サーバ bond は 9000 であり、サーバ向け Leaf の MTU が不一致だった。
Po11 を **9216** に修正し、member の実 MTU も 9216 に追従することを確認した。
既に channel-group に属する物理 interface への直接 `mtu` 指定は拒否されたため、実投入は Po11 側で行った。

| 再試験 | 結果・判定 |
|---|---|
| IP 全長 1,400〜8,900 byte、3 経路、IPv4／IPv6、各 3 packet | 60 条件／180 packet すべて成功。修正前は 1,501 byte 以上の全条件で応答なし |
| 通常 MSS の TCP 256 KiB、低レート UDP 1,200／8,000 byte | 18/18 条件で全量回収 |
| 以前と同じ TCP 比較 | 23/24 条件で全量回収。1 条件は送信 0／errors 1。負荷停止後の同条件再確認は 2/2 成功 |
| UDP 20 Mbps | 未回収率 0〜100%。高レートの性能受入は未完了 |
| 同セッションの LB | 72/73 成功。負荷比較後に 1 回 timeout、10 秒待機後と最終確認は成功 |

サイズ依存の失敗は今回の測定範囲で解消した。経路全体の最大 MTU 9216 や PMTUD の正常性まで確認した結果ではない。
高負荷での損失・一時 TCP／LB エラーは `TI-004` に残す。測定ツールの終了コードだけで判定せず、
送受信量、echo の内容、error、capture と比較した。

## 4. 保存 config と終了時の状態

| 対象 | 終了時の扱い |
|---|---|
| NX-OS Egress 設定 | 常設の受信許可・集約を維持。k02／k03 の IPv4 `/24 le 32`、IPv6 `/64 le 128` に統一、route-map permit 10 → 20 → 30 |
| 広報範囲 | Egress 専用 no-export・専用 import 除外は撤去。LB と同じ既存 VRF／EVPN／DCI 方針に従う。k03 の BGP endpoint 保護用 no-export は別用途で維持 |
| 集約 | 個別経路と集約を併存。`summary-only` による個別経路抑止は未採用。LB 既存 permit 10／20 は維持 |
| Leaf サーバ向け MTU | single-site 2 台の running-config と、single-site／multisite 両 AS 方式の計 6 config に反映。**追加 MTU 変更の startup-config 保存は未実施** |
| multisite | BDC の k03 BGP 基盤も基本 config に反映。`as-equals` と正規生成した `as-changes` を整合。実機投入なし |
| 一時リソース | 試験用 Egress Policy／advertisement／`egress0`／namespace／専用サーバを撤去。常設 BGP 設定と LB は維持 |
| checksum | 両 worker の off 設定と条件付き監視を維持。Node／kernel の変更なし |
| Git | 生ログ・runtime・実環境の登録 state は除外。今回は stage／commit／push を実行していない |

以前の Node-facing MTU や Egress BGP 設定の startup 保存履歴と、今回のサーバ向け MTU 未保存は区別する。

## 5. 残課題・次回の再開点

| 項目 | 状態 | 次に判断・確認すること |
|---|---|---|
| `TI-001` IPv6 checksum | `Workaround validated` | off＋監視を維持。kernel／Cilium の恒久候補は別枠で評価 |
| `TI-002` RIB／Forwarding・ECMP | `Open` | 計画退避、withdraw、残存 path、FIB と実通信を対応付ける |
| `TI-003` CoreDNS | `Workaround validated` | 環境ごとに到達可能な upstream を実測し、runtime 設定で管理 |
| `TI-004` 高負荷性能 | `Open` | サーバ側 MTU 1500 の不一致は修正済み。TI-007 の確認後、rate／packet 数を段階的に変え、仮想 Fabric の queue／drop と LB 影響を照合 |
| `TI-005` 管理側 VXLAN | `Open` | 設計を変更するか稼働値を変更するかを決める。今回 Node 設定を変更していない |
| `TI-006` 新規 Pod 初回 timeout | `Open` | identity／Policy／接続開始時刻と timeout 原因を再測定 |
| [TI-007](test-issue-register.md#ti-007-mtu-9100) MTU 統一・境界試験 | `Open`（未適用・未試験） | 次回最優先。Node／他サーバ向け Po11〜16 を MTU `9100` に統一するための影響確認・config 修正・適用後、IP 全長 `8999`／`9000`／`9001` byte の境界と低レート通信・API／BGP／LB 回帰を確認 |
| 全体 connectivity | 未合格 | HostPort 宛先と公開範囲を整理し、最新 CLI で再受入。過去 drop と今回増分を分離 |
| 証跡完全性 | 一部保留 | TG の不足原本／転送元ハッシュを確認。機能試験をやり直す前に保存物を照合 |
| SNAT port 枯渇 | 未実施・保留 | 通常経路の損失を説明できてから実施枠を決める |
| Node 障害・復旧、kernel 更新 | 今回 skip | 明示的に再計画するまで実施しない |
| multisite／Cluster Mesh | 実測未実施 | single-site の残課題・開始条件を確認してから起動・実測する |

次回は `TI-007` を最初に実施し、その後に `TI-004` の段階的負荷確認と `TI-005` の設計判断を進める。
長時間の全体試験と保留試験は別枠とする。詳細は [試験課題台帳](test-issue-register.md) を参照する。

## 6. 証跡の所在と完全性

生ログ・実行コマンド・実時刻・集計は Git 管理外に保存する。

```text
nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-09-05/adc-k02/
nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/
```

| 入口となる結果文書 | 内容 |
|---|---|
| `2026-09-05/adc-k02/tg01-result.md`〜`tg08-result.md` | TG ごとの判定と転送・ハッシュの制約。TG-00 は同ディレクトリの `README.md` |
| `2026-09-06/adc-k02/connectivity-full-result.md` | 全体試験の実行コマンド、4 tests の失敗、終了状態 |
| `connectivity-cli-fix-result.md` | `.3` の限定 114 actions と変更した判定条件 |
| `offload-regression-result.md`／`checksum-monitor-result.md`／`checksum-pod-restart-result.md` | checksum 回避策・監視・Pod 再作成の各結果 |
| `egress-gateway-result.md`／`egress-cidr-outside-result.md`／`egress-invalid-result.md` | 基本・CIDR 外・異常設定の試験 |
| `egress-remaining-result.md`／`egress-mtu-result.md`／`egress-mtu-fix-result.md` | 残項目、修正前の MTU 境界、修正後の再試験 |

表で日付ディレクトリを省略した文書は `2026-09-06/adc-k02/` 内にある。
最終 MTU セッション `raw/egress-mtu-fix-NIVXUbvH/` は **1,702 ファイル**を実行ホストと転送後にハッシュ照合済み。
準備終了時の並行書込みで commands／requests 索引の一部が置き換わった制約は `evidence-index-notes.md` に明示し、
原本の HTTP／access log、source、別途照合した 12 HTTP を保持した。完全なコマンド索引とは扱わず、推測による補完はしていない。
この局所的な照合成功を、過去を含む全証跡の完全性確認済みという主張へ広げない。

公開する本書は判定と条件を要約したもので、生ログや認証情報を同梱しない。
コード・設定の保存前確認は Git 管理外の [更新レビュー](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/git-review-2026-09-07/git-review-2026-09-06.md) に記録する。
