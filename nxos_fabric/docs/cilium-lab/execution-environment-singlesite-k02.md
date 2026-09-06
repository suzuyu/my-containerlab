# 実際の試験環境：single-site k02

この文書は、今回の試験で使う実行ホスト、ローカル作業環境、配置パス、ファイル転送の運用をまとめる。
記録日付は 2026-09-06。接続情報はユーザーから提示されたものを使用し、同日に clab01 へ接続して
更新ファイルの配置、事前確認、Egress Gateway の基本試験と撤去を実施した。試験の目的・操作・判定は [Egress Gateway 構築・試験手順](egress-gateway-test-plan.md) を参照する。

別環境で流用するときは、この環境メモを複製して値を変更し、手順へ渡す環境変数を設定する。
個人のユーザー名やホームディレクトリは、共通手順の前提にしない。

## 1. ホストの役割と配置

| 項目 | 今回の値・運用 |
|---|---|
| ラボ実行ホスト | `clab01`、管理 IP `192.168.129.59` |
| SSH 接続 | `suzuyu@192.168.129.59`。登録済み鍵による認証を使用する |
| 端末 A／B | どちらも `clab01` に接続した shell。実行ホスト上の同じファイルと Docker 環境を使う |
| 実行ホストのリポジトリ | `/home/suzuyu/containerlab` |
| ローカル作業環境のリポジトリ | `/home/suzuyu/my-containerlab` |
| topology | `nxos_singlesite` |
| cluster／context | `adc-k02`／`kind-adc-k02` |
| CLI 配置 | 実行リポジトリ配下の `nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin` |
| コードの配布 | ファイルを直接転送する。実行サーバの Git 同期は前提にしない |
| 証跡 | 実行ホストに保存し、確定後にローカル作業環境へ転送する |

SSH 秘密鍵、token、kubeconfig の認証データはこの文書へ記載しない。
同じラボ内の Gateway Node 名・IP 割り当ては [アドレス台帳](parameter-and-address-allocation.md#5-egress-gateway) で管理する。

<a id="environment-variables"></a>

## 2. 環境変数

**端末 A／B のそれぞれで、clab01 に接続した後に実行する。**
このブロックは今回の配置先に対応する設定であり、試験 resource は変更しない。

```bash
export REPO_ROOT=/home/suzuyu/containerlab
export KUBE_CONTEXT=kind-adc-k02
# 今回の継続試験の記録日。実時刻は各ログへそのまま保存する。
export TEST_DATE=2026-09-06
export KUBECONFIG="${REPO_ROOT}/nxos_fabric/nxos_singlesite/clab-nxos-fabric-singlesite/adc-k02/k8s_kind/k02/kubeconfig-k02"
```

その後、[共通手順 2：環境設定と証跡](egress-gateway-test-plan.md#egress-session) へ戻る。
端末 B で試験セッションを作り、両端末で読み込む。
CLI の `PATH`、試験日の `TEST_DATE`、証跡先の `EG_DIR` は手順内で設定・保存する。

## 3. コード配置と証跡転送

Egress Gateway 試験前に、次のファイルをローカル作業環境から実行ホストの同じ相対パスへ転送する。
手順だけ新しく、manifest／スクリプトが古い状態で実施しない。

- `nxos_fabric/docs/cilium-lab/egress-gateway-test-plan.md`
- `nxos_fabric/docs/cilium-lab/egress-gateway-routed-design.md`
- `nxos_fabric/nxos_singlesite/configs/changes/cilium-stage2b/` 配下
- `nxos_fabric/docs/cilium-lab/execution-environment-singlesite-k02.md`
- `nxos_fabric/nxos_singlesite/k8s_kind/k02/cilium/manifests/validation/egress/` 配下
- `nxos_fabric/scripts/cilium-lab/configure-egress-gateway-addresses.sh`

今回の証跡パスの対応は以下のとおり。`<TEST_DATE>` と `<session>` は手順で実際に生成した値を使う。
日付をまたいでも、端末 A で新しい日付を計算して別セッションへ変更しない。

| 保存場所 | パス |
|---|---|
| 実行ホスト | `/home/suzuyu/containerlab/nxos_fabric/nxos_singlesite/operations/cilium-lab/<TEST_DATE>/adc-k02/raw/<session>/` |
| 転送後のローカル作業環境 | `/home/suzuyu/my-containerlab/nxos_fabric/nxos_singlesite/operations/cilium-lab/<TEST_DATE>/adc-k02/raw/<session>/` |

端末 A の外部サーバログ保存と後片付けまで終わってから `SHA256SUMS` を確定し、セッションディレクトリ全体を転送する。
転送後はそのディレクトリ内で `sha256sum -c SHA256SUMS` を実行する。
共通手順の相対パス方式により、実行側とローカル側でリポジトリの絶対パスが違っていても照合できる。
`operations/` 配下の証跡は Git へ追加しない。

## 4. 準備時点の記録（基本試験前）

- 90 分上限の全体 connectivity test は他の検討・機能確認の後に実施する。全体試験を合格済みとは扱わない。
- Egress Gateway の基本試験を、設定・経路・待受確認と Policy 未適用 baseline から開始する。
- 以前の TG 試験専用 HTTP サーバは終了済み。Egress 手順では専用の TCP `8088` を使って待受を準備する。
- 手順・manifest・IP 設定 script・NX-OS 差分の 27 ファイルを転送し、ハッシュ照合済み。変更前ファイルは証跡内へ退避した。
- 手順 2～6 を実施済み。`egress-probe` の 2 Pod は worker2 で Ready、外部サーバ 2 台の TCP `8088` を準備し、baseline 8 件が HTTP 200。
- 新しい `egress0`、BGP advertisement、Egress Policy、NX-OS 差分は未適用。次は手順 7 から再開する。
- 既存 `lab-smoke-lb-cluster` の IPv6 は変更前からタイムアウトが混在した（初回失敗、再確認 3 件中 2 成功・1 失敗）。LB 回帰項目を全面合格にはしない。原因と既知課題との同一性は未確定。
- Node 停止・反映遅延などの追加試験は、基本試験と分けて実施枠を決める。

上記は今回の作業状況であり、別環境での必須の実施順や構築済み状態を示すものではない。

## 5. 2026-09-06 の試験セッションと完了状態

試験セッションは `egress-stage2b-xtu86wy1`。実行側の保存先は
`nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/raw/egress-stage2b-xtu86wy1/`。
準備証跡を保持したまま、今回の再開分を `execution/` 配下へ保存した。
このセッションの基本試験と撤去は完了済み。再試験時は手順 2 から新しいセッションを作り、Pod と HTTP 待受も準備し直す。

- `baseline-result.json`：`W-EGRESS-01` の 8 件の結果。
- 通常の IPv4 送信元：`172.16.4.22`。IPv6：`fd21::4:0:0:2:2`。
- `limited-recheck.json`：既存 LB IPv6 の限定再確認。
- `preparation-result.md`：完了・未実施の境界と再開方法。
- `transfer/`：転送 manifest、旧ファイル、ハッシュ照合記録。

試験 Pod、Namespace、専用 TCP `8088` 待受、Egress Policy、試験用 BGP advertisement、
両 Node の `egress0`、両 BGR の専用 prefix-list／permit 30 は撤去済み。
試験前の Namespace 未作成による server dry-run／diff エラーは、Namespace 作成後の再確認で解消した。

## 6. 基本試験の結果（2026-09-06）

[実行結果・コマンド・残課題](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-gateway-result.md) を正本とする。
生ログは同セッションの `execution/`、最終ハッシュはセッション直下の `SHA256SUMS` に保存する。

- baseline 8 件、`gw-a` 4 件、除外宛先 2 件、`gw-b` 4 件、Policy 撤去後 8 件の計 26 件が成功。外部 access log の試験 ID と送信元も一致した。
- 専用 `/32`／`/128` の BGP 広報・各所有 Node への next-hop・撤回を両 BGR／両 Leaf で確認した。既存 LB 集約経路は維持した。
- Cilium Agent の UID・再起動回数・ConfigMap は変更なし、Node は 3 台 Ready、BGP は 8 セッション Established。
- 既存 LB IPv6 `Cluster` VIP は、今回の直前確認では成功、撤去後はタイムアウト、追加 3 件は 1 成功・2 失敗。IPv6 `Local` は追加 3 件とも成功した。準備時にも混在した事象であり、Egress の基本通信とは分けて LB 回帰項目を未合格とする。
- `W-EGRESS-04` は `excludedCIDRs` のみ確認。CIDR 外、無効 Gateway、起動時の反映遅延、Node 停止、自動 HA、既存長時間接続、SNAT 枯渇、物理経路の packet capture／counter は未実施。

全体 connectivity test は、この基本試験より前に 90 分上限で実施済み。全体結果と試験用 CLI の限定修正は
同日の `connectivity-full-result.md`／`connectivity-cli-fix-result.md` を参照する。準備時点の「後日実施」と現在の状態を混同しない。

## 7. 常設 config への移行（2026-09-06、基本試験の後）

[常設設定の適用結果・コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-default-config-result.md) を参照する。
セッションは `egress-defaults-VieOtLoe`。5 節の撤去は以前の基本試験終了時の状態であり、常設化直後は以下に更新した。広報方針の最新状態は 8 節を参照する。

- ADC BGR 2 台の Egress 受信許可と `/24`・`/64` 集約、ADC Leaf 4 台の controller VRF 除外、Leaf 0101/0102 の no-export 付与を常設した。6 台とも startup-config へ保存済み。
- Node の個別経路と NX-OS の集約が併存すること、Leaf の controller VRF に入らないこと、tenant BGP の community を確認した。
- 一時的な Node IP と BGP advertisement は撤去済み。全 contributor の撤回後に個別経路と集約も消え、NX-OS 設定だけが残ることを確認した。
- 次の Egress 試験では手順 2 から新しいセッションを準備し、手順 7 は常設 NX-OS 設定の確認から進める。通常の後片付けで NX-OS rollback を実行しない。
- multisite は基本 config の更新まで。`as-equals` と生成した `as-changes` を用意したが、停止中のため実機投入・起動・DCI の動作確認はしていない。

`summary-only` は未設定で、経路数の削減はまだ行わない。片系 peer 断などで個別経路を失う場合の戻り通信を確認してから、抑止条件を別変更で決める。

## 8. Egress の no-export 撤去（2026-09-06、常設化の後）

Egress IP の広報を LB IP と同じ扱いに変更した。
[修正結果・実行コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-export-policy-result.md) を参照する。
セッションは `egress-no-export-2p741AgV`。7 節の Egress に対する no-export 付与は現在は撤去済みである。

- single-site の Leaf 0101/0102 で専用 route-map と neighbor の参照を削除し、startup-config へ保存した。
- Leaf 4 台で、個別 4 経路と集約 2 経路の伝播と no-export が付かないことを確認した。
- 一時広報と Node IP は撤去済み。Cilium の UID・再起動回数・設定に変化なし、BGP 8 Established を維持した。
- LB 4 宛先は今回各 1 回成功。既存 IPv6 Cluster VIP の間欠障害が解消したとは扱わない。
- multisite は config のみ更新。DCI advertised-routes・対向 tenant RIB・戻り通信は起動後に確認する。

Egress 受信許可・集約併存・controller VRF の import 除外は維持する。k03 接続用 loopback の no-export は別用途のため残す。

## 9. IPv4 Egress filter の簡略化（2026-09-06）

最新の IPv4 方針は [変更結果・コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-v4-filter-result.md) を参照する。
セッションは `egress-v4-simplify-gi2PNpUh`。8 節までの IPv4 import 除外はこの変更で撤去する。

- BGR の `CILIUM_K02_EGRESS_V4` は `seq 5 permit 172.16.24.0/24 le 32` の 1 行に統合する。
- Leaf の `CILIUM_EGRESS_SCOPE_V4` と `IPv4_IMPORT_MAP_controller-vpc1 deny 5` を削除する。
- Egress の IPv4 `/24` 集約は既存の import 条件で controller VRF にも入り、全 contributor 撤回時に消える。
- IPv6 の受信許可・import 除外、k03 の受信範囲、LB filter、集約と個別経路の併存は維持する。
- multisite は保存 config の更新までで、実機への投入は行わない。

Node への IP 割当や広報を自動で増やす変更ではない。集約のみの広報への切替は別の変更として扱う。

このセッションの single-site 6 台は適用・startup 保存・一時 resource 撤去まで完了した。
IPv4 Cluster／Local と IPv6 Local の LB 確認は成功し、IPv6 Cluster はタイムアウトした。以前からの間欠事象との因果関係は未特定で、残課題として記録する。

## 10. IPv6・k03 の範囲統一と route-map 順序（2026-09-06）

最新の両 family の方針は [変更結果・コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-range-unification-result.md) を参照する。
セッションは `egress-ranges-OUXQThcZ`。9 節まで残していた IPv6 の Egress 専用 import 除外も削除する。

- k02：IPv4 `172.16.24.0/24 le 32`、IPv6 `fd21:0:0:24::/64 le 128`。
- k03：IPv4 `172.16.25.0/24 le 32`、IPv6 `fd21:0:0:25::/64 le 128`。
- 各 Egress prefix-list は sequence 5 の 1 行とする。
- `CILIUM_K02_IN_V4/V6`／`CILIUM_K03_IN_V4/V6` を同じ名前ごとにまとめ、permit 10 → 20 → 30 の順に記載する。
- Leaf の IPv4／IPv6 Egress 専用除外は両方なくなり、既存 import policy に従う。k02 の Leaf 4 台では IPv6 集約の controller VRF への取り込みも確認した。
- multisite は保存 config の更新までで、実機への投入は行わない。

LB filter、集約と個別経路の併存、k03 の BGP 接続用 loopback の制御は維持する。

このセッションは single-site 6 台の startup 保存と一時 resource 撤去まで完了した。
BGP 8 Established と Cilium の状態を維持し、今回の LB 4 宛先は成功した。過去の IPv6 Cluster VIP の間欠事象が解消したとは判断しない。

## 11. IPv6 VXLAN checksum 回避策と回帰（2026-09-06）

10 節までの IPv6 Cluster VIP の間欠障害は、[offload 比較](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/lb-ipv6-offload-result.md) で
Node 間転送と checksum offload の組合せに絞った。
今回の [回避策適用後の回帰結果](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/offload-regression-result.md) は
セッション `offload-regression-rqz0oAeF` に保存する。

- `adc-k02-worker`／`adc-k02-worker2` の `cilium_vxlan` は `tx-checksum-ip-generic: off` を維持する。
- Service／NodePort 等 114 actions、Egress 46 HTTP、LB 42 HTTP が成功した。IPv6 Cluster VIP は別 Node の backend への両方向を含む。
- 一時的な Egress Policy、advertisement、専用 Node IP、試験 Pod、HTTP server は撤去した。NX-OS 常設設定は維持する。
- 短時間負荷は通信失敗 0 だが、off 側の平均処理率は約 11.4% 低かった。最大性能や offload 単独の影響を確定した比較ではない。
- 回避策は runtime 設定。Node／interface 再作成後の自動再適用、kernel 更新、Cilium 恒久修正は未実施。

次は [kernel 判定と対応方針](kernel-compatibility-policy.md) に従い、互換設定の維持・解除条件を整えてから、Egress の残りの受入を進める。
停止中の multisite へ runtime 変更は行っていない。

## 12. 回避策の再適用監視と kernel 候補評価（2026-09-06）

11 節の後に [再適用監視を導入・検証](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/checksum-monitor-result.md) した。
現在は `cilium-checksum-adc-k02.timer` が user unit として有効で、登録条件が一致する場合だけ 30 秒周期で再適用する。
ユーザー `suzuyu` の linger は no → yes に変更した。停止・解除手順は [運用手順](checksum-compat-operations.md) を参照する。

- 設定ずれの検出、timer による自動修復、未承認 kernel 条件での適用拒否を確認した。
- 再適用後の LB は 42 HTTP 成功。Node 間 IPv6 の両方向と受信 checksum を確認した。
- Node／ホストの実再起動、kernel 更新、Cilium upgrade は未実施。再適用までの通信を自動遮断する機構ではない。
- `5.14.0-687.44.1.el9_8` の公式 source RPM にも `BPF_F_IPV6` の受入がなく、今回の修正済み更新先とは扱わない。

証跡は `raw/checksum-monitor-veu11iby`。
稼働 state は `/home/suzuyu/containerlab/nxos_fabric/nxos_singlesite/operations/cilium-lab/runtime/adc-k02/checksum-compat.json` に保存する。
最新の恒久候補の評価は [kernel 候補調査](kernel-checksum-candidates.md) にまとめる。

## 13. Cilium Pod 再作成後の checksum 維持確認（2026-09-06）

[動作試験結果・実行コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/checksum-pod-restart-result.md) に記録した。
証跡は `raw/checksum-pod-restart-x04zew4o`。

- worker は `cilium-4kv79` → `cilium-9nwg2`、worker2 は `cilium-jkqzx` → `cilium-qxq6d`。1 台ずつ再作成し、約 17 秒で Ready を確認した。
- VXLAN interface と `tx-checksum-ip-generic: off` が維持され、監視は新しい Pod UID を認識した。再書き込みは不要だった。
- 再作成中の HTTP 208 件と復旧後の HTTP 84 件は成功。IPv6 Cluster の受信 SYN/ACK 48 件は checksum correct で、Node 間転送の両方向を確認した。
- 最終状態は Cilium 3 Pod Ready、BGP 8 Established。DaemonSet／ConfigMap／image と互換設定の登録内容は変更していない。
- kernel 変更、kind worker・実行ホスト・containerlab の再起動は実施していない。監視 timer と off 設定を維持する。

## 14. 宛先 CIDR 外の Egress 比較（2026-09-06）

[追加試験結果・コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-cidr-outside-result.md) に記録した。
証跡は `raw/egress-cidr-outside-8oPoHTOX`。以前の基本試験で未実施だった CIDR 外の項目を追加確認した。

- `adc-t1sv0201` の `172.16.1.1`／`fd21:0:0:2::101` は、既存 Policy の対象 CIDR 外。同じ tenant の別ネットワークである。
- TCP `8088` の今回専用 nginx を 3 台に一時起動し、対象内・明示除外・CIDR 外を同じ selected／unselected Pod から比較した。
- baseline／gw-a／gw-b／Policy 削除後の 48 HTTP はすべて成功し、外部 access log の送信元・ID・status と一致した。
- CIDR 外・除外先では通常 Node IP を維持し、selected の対象内通信だけが指定 Egress IP に変わった。前後の LB 8 HTTP も成功した。
- 試験 Policy、advertisement、namespace、`egress0`、専用 nginx は撤去した。NX-OS 常設設定、checksum off と監視を維持した。
- Node InternalIP の現値は管理側。`build-plan.md` の Fabric 側指定との不一致は設計照合待ちとして記録し、稼働設定は変更していない。

## 15. Gateway／Egress IP 選択不能時の拒否（2026-09-06）

[試験結果・コマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-invalid-result.md) に記録した。
証跡は `raw/egress-invalid-ByUgGZaH`。実施構成の図と端末 A/B 手順は [12.1～12.4 節](egress-gateway-test-plan.md#121-異常系-2-ケースの共通準備) にある。

- Gateway selector 不一致は worker2 で `194 / NO_EGRESS_GATEWAY`、worker に存在しない IP の指定は worker で `204 / DROP_NO_EGRESS_IP`。
- 各ケースで selected の IPv4／IPv6 各 3 接続が拒否され、対象外・除外先・CIDR 外の比較通信各 10 件は成功した。
- 復旧後は各 12 HTTP が指定送信元で成功。前後・復旧・比較・LB を含め 88 成功と 12 拒否、計 100 接続が期待どおりだった。
- 一時 Policy・advertisement・namespace・`egress0`・HTTP サーバ・Relay 転送は撤去済み。Node label、Cilium、NX-OS の常設設定と checksum 回避策は維持した。
- 新規 Pod 以降の追加試験は次節へ記録した。Node 停止／kernel 変更は引き続き今回の対象外。

## 16. Egress 残項目とサイズ・負荷問題（2026-09-06～07）

[実施結果・コマンド・出力例](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-remaining-result.md) は残項目の先行結果。最新の MTU 切り分けと手順検証は 17 節を参照する。
証跡は `raw/egress-remaining-o46v5mCO`。日付をまたいだが保存先は開始日の `2026-09-06/adc-k02` とした。

- 新規 Pod は 3 回、IPv4／IPv6 の 240 HTTP が初回から指定 Egress IP。外部 access log と全件一致。
- BPF map、Node capture、BGR 2 台・Leaf 4 台の経路／counter を照合。Node 間は管理側 eth0 の VXLAN、外部への送信は Fabric NIC。
- 計画切替時の既存 TCP は IPv4／IPv6 とも reset。切替先 IP の新規接続は成功し、アプリケーションの再接続が必要。
- 大きい TCP／UDP は 48 条件実施して未合格。Policy なしでも失敗し、負荷後の LB で 1 回 timeout。停止後は連続 12 回と撤去前後の 8 回が成功。
- TCP の試験 socket だけ MSS 1200 にすると 256 KiB 転送成功。UDP 0.1 Mbps は 1,200／1,400 byte 成功、8,000 byte 失敗。恒久 MTU／MSS 設定は変更していない。
- [TI-004](test-issue-register.md#ti-004-large-packets) の切り分けを優先し、SNAT port 枯渇は未実施・保留。Node 障害・復旧は依頼どおりスキップ。
- 試験リソース撤去、Cilium 3 Pod Ready、BGP 8 Established、checksum off の維持を確認。Node／ホスト再起動・kernel 変更なし。
- 1,482 ファイルを転送元の SHA256SUMS と照合済み。全項目合格としては扱わない。


<a id="egress-probe-build"></a>

## 17. 追加測定用バイナリの配置と 2026-09-06 の MTU 結果

`clab01` には Go が標準 PATH にないため、Linux amd64 の測定バイナリを作業環境で作り、直接転送した。
[ソース](../../scripts/cilium-lab/egress-probe.go) とバイナリのハッシュを実行セッションへ保存する。
今回のコンパイラは Go `1.27.1`。別の Go で再ビルドしたバイナリは別ハッシュになるため、その版とハッシュを新たに記録する。

**準備用の作業端末（ローカル）：** Go を使える環境で実行する。この準備だけは実行ホストの端末 A／B と区別する。

```bash
(
  set -euo pipefail
  cd /home/suzuyu/my-containerlab
  command -v go
  probe_build="$(mktemp -d /tmp/egress-probe-build-XXXXXXXX)"
  go version > "$probe_build/go-version.log"
  cp nxos_fabric/scripts/cilium-lab/egress-probe.go "$probe_build/"
  CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GO111MODULE=off go build -o "$probe_build/egress-probe" "$probe_build/egress-probe.go"
  (cd "$probe_build" && sha256sum egress-probe.go egress-probe go-version.log > SHA256SUMS)
  scp "$probe_build/egress-probe" suzuyu@192.168.129.59:/home/suzuyu/containerlab/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin/egress-probe
  scp "$probe_build/egress-probe.go" suzuyu@192.168.129.59:/home/suzuyu/containerlab/nxos_fabric/scripts/cilium-lab/egress-probe.go
  printf 'build=%s\n' "$probe_build"
  cat "$probe_build/SHA256SUMS"
)
```

**端末 B（clab01）：** 次のハッシュを準備側の同名ファイルと照合してから、共通手順 12.5 へ進む。

```bash
sha256sum \
  "$REPO_ROOT/nxos_fabric/scripts/cilium-lab/egress-probe.go" \
  "$REPO_ROOT/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin/egress-probe"
"$REPO_ROOT/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin/egress-probe" help
```

今回の手順レビューでは共通準備、新規 Pod、経路 capture、既存 TCP 切替、低レート MTU 境界、撤去のコマンドを実行ホストで検証した。
測定サーバには `/source` を追加し、手順を単独で再現できるようにした。元の試験の source・binary は raw にそのまま残す。

最新結果は [MTU 境界とパケットサイズの結果](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-result.md)。
記録日 `2026-09-06`、取得時刻は実際の UTC／JST。Leaf0103／0104 の server 側 `port-channel11`／`Ethernet1/1` が MTU 1500、Node 側は 9216。
IP 全長 1500 は成功、1501 以上は失敗。MTU 設定は変更していない。高負荷比較・SNAT port 枯渇の再開と Node 障害系は保留する。

手順検証の新規 Pod は 239/240 成功、最初の IPv4 timeout 1 件を [TI-006](test-issue-register.md#ti-006-newborn-first-request) に保存した。初期失敗と後続安定を分けて判定する。


<a id="latest-egress-results"></a>

## 18. 2026-09-06 の記録：Leaf MTU 修正後の再試験

[MTU 修正・再試験の結果とコマンド](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/egress-mtu-fix-result.md) が最新。
`adc-lfsw0103`／`0104` の server0102 向け Po11 を MTU 9216 に変更し、Ethernet1/1 の実 MTU も 9216 になった。
single-site と multisite の as-equals／as-changes、計 6 保存 config を直接転送・照合した。multisite の live 環境は変更していない。
startup-config への保存は実施していない。

3 経路・両 family の IP 全長 1,400〜8,900 byte が全成功。低レート TCP／UDP も 18 条件で全量回収。
48 条件の高レート比較の損失は別判定とし、最終集計は上記結果を参照する。Node／kernel／containerlab は再起動していない。
試験日ラベルは 2026-09-06、実時刻は各ログの UTC／JST に保持した。
