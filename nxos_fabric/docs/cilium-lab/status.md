# Cilium ラボの現在のステータス

最終実測：2026-09-13（single-site 終了時確認、multisite k01 MetalLB 調査、k02／k03 導入と Cluster Mesh 基本通信）。
single-site `adc-k02` は既知課題付きで一区切りとし、multisite の構築へ移った。
multisite はユーザーが clab02 で CDC 除外版を起動し、構築中。
checksum 適用手順と一括 driver を準備済み。[CDC 除外・k01 維持版](design/multisite-clab02-startup-options.md) の YAML と機器台帳を作成し、静的検査を完了した。
3 サイト版・CDC 除外版の両 YAML は NX-OS `10.6.4.M.lite` を指定する。
[k01 MetalLB の限定調査](results/multisite/2026-09-13/k01-metallb-neighbor-investigation.md) では 12/12 BGP Established を確認したが、初回 ARP／ND 解決の問題が残る。Cilium／Cluster Mesh の受入結果とは分ける。
[multisite k02 の初回導入](results/multisite/2026-09-13/k02-initial-install.md) では Cilium／Hubble／Tetragon と LB／BGP の基本確認を完了した。
BGP は逆方向 ping 後に 8/8 Established。
[k03 導入・Cluster Mesh 確認](results/multisite/2026-09-13/k03-clustermesh-install.md) では
BDC Leaf の MTU、Mesh の名前解決と API 更新方式を修正し、両サイトで agent 3/3・KVStoreMesh 2/2 の相互接続を確認した。
サイト間 Pod HTTP 16/16、Global Service HTTP 8/8、外部 k03 LB HTTP 12/12 が成功。
両サイトの Cilium は OK で remote cluster error は解消した。性能・障害系・全体 connectivity は未受入。

[09-13 の保存時点](results/multisite/2026-09-13/checkpoint.md) に、終了時の追加確認、
一時リソースの扱い、Git 保存範囲と次の区切りへ回す作業をまとめた。
自動試験用 `cilium-mesh-bootstrap-check` は両サイトから撤去済み。
UI 用 `cilium-test` を保持し、撤去後も Mesh 接続と各 8/8 BGP Established を確認した。
後続の保存操作で、clab02 の BDC Leaf0101／0102 は startup-config への保存を完了し、
Po14〜16 の `mtu 9216` を startup-config でも確認した。

## single-site の直近の結果

- 09-13 の終了時確認は 69 件成功。Node 3 台 Ready、Cilium 3/3、BGP 8 セッション Established。既存 LB の IPv4／IPv6 HTTP は 40/40 成功（09-12 撤去後の 232/232 とは別測定）。
- topology／values／manifest／Leaf 保存 config の 15 ファイルは実行ホストとローカルで同一ハッシュ。今回の証跡も転送後のハッシュ照合済み。
- connectivity 全体は **80/82 tests 成功、2 tests／3 actions 失敗**。試験用 Pod の旧 IP を修正した限定再試験は **1 test／6 actions 成功**。全体合格とはしていない。
- MTU 到達性と Egress 初期化は確認済み。性能受入は未完了で、Fabric 内の遅延・順序逆転、欠落区間、socket 側の未回収を継続調査する。
- 一時試験リソースは撤去済み。Egress 初期化 DaemonSet と `egress0`、checksum 回避策は維持している。

| 詳細結果 | 内容 |
|---|---|
| [終了時確認・multisite 引継ぎ](results/singlesite/2026-09-13/singlesite-closeout-2026-09-13.md) | 09-13 の簡易確認、保存設定照合、残課題と移行手順 |
| [設定照合・全体回帰・性能切り分け](results/singlesite/2026-09-12/singlesite-regression-validation-2026-09-12.md) | 最新の全体試験、限定再試験、UDP／TCP の比較、最終状態 |
| [検証ステータス](results/singlesite/2026-09-12/validation-status-2026-09-12.md) | MTU、LACP、Fabric 経路への修正 |
| [Egress 初期化の統合試験](results/singlesite/2026-09-12/egress-interface-init-validation-2026-09-12.md) | 初回適用、設定変更、明示 rollout の確認 |
| [過去の結果一覧](results/README.md) | 以前の失敗を含む日付別記録 |

## Stage ごとの進捗

Leaf L2 MTU `9216`、Node Fabric MTU `9150`、Cilium 基準 MTU `9050`、Pod 経路 MTU `9000` を採用した。
以前の Po MTU `9100` 統一案は現行設計ではない。TI-007 の MTU／LACP と TI-005 の Fabric underlay 修正は
[2026-09-12 検証ステータス](results/singlesite/2026-09-12/validation-status-2026-09-12.md) で確認済み。

- [x] Leaf の対象 Po／LACP と Node Fabric／Cilium の MTU を保存設定・稼働環境へ反映する。Leaf の最新変更の startup-config 保存は別途未実施
- [x] 通常／gw-a／gw-b、IPv4／IPv6 の IP 全長 `9000` byte 到達と `9001` byte のローカル拒否、低レート TCP、API／BGP／LB 回帰を確認する
- [x] Node InternalIP と Cilium VXLAN 終端を Fabric IP へ合わせ、対象通信の管理側 `eth0` への流出がないことを確認する
- [x] Egress 初期化 DaemonSet の初回適用・設定変更・明示 rollout を確認する（[統合試験結果](results/singlesite/2026-09-12/egress-interface-init-validation-2026-09-12.md)）

Stage 1〜4 は single-site の保存済み結果に基づく。各 Stage の詳細なチェックリストは
[構築計画](build-plan.md) で管理する。過去の失敗は証跡に保持し、後続結果で確認できた範囲だけを更新する。

| Stage | 現状 | 残りの中心 |
|---|---|---|
| 1 基盤 | Fabric InternalIP／VXLAN、MTU 境界、基本疎通と限定回帰は確認済み。全体試験は未合格 | 累積 drop 検出を含む全体受入、API 経路切替、経路途中の PMTUD |
| 2A LB／BGP | 基本疎通と checksum 回避策下の Node 間 IPv6 LB は成功 | 未割当 VIP、経路退避・障害・広告変化の受入 |
| 2B Egress | 基本機能、新規 Pod、実経路、計画切替の既存接続を確認。9000 byte 到達は確認済み、性能受入は未合格 | TI-004 の Fabric 遅延・順序逆転・欠落区間、socket 側未回収、TCP 再送。SNAT port 枯渇・Node 障害系は保留 |
| 3 Hubble／Policy | NP-00〜NP-07 の既存合格を継承。Relay と後続の限定回帰も成功 | UI 接続経路、追加 resource 評価。今回全 NP を再実行したわけではない |
| 4 Tetragon | TG-00～TG-08 の記録した観測・短時間負荷・停止復旧は合格 | 一部原本の転送元ハッシュ照合。accept 観測や長期負荷は確認範囲外 |
| 5～6 multisite／発展 | k02／k03 の常設基盤、CA 共有、Mesh 相互接続と双方向の基本通信を確認 | API／経路／サイト障害、Global Service fallback、MTU 境界・性能、初回 ARP／ND と Node IP 初期化の再現性 |

## 次に進める作業

1. Cluster Mesh API の片系停止・復旧、経路退避とサイト断、Global Service の local 優先／remote fallback を段階的に確認する。受入条件は [Cluster Mesh 設計](design/clustermesh-fabric-dci-and-acceptance.md) に従う。
2. サイト間の MTU 境界と性能、資源使用量を測定する。k01／k02 の初回 ARP／ND 解決と、k02／k03 で kubelet Node IP が未反映だった原因も継続調査する。
3. [multisite checksum 手順](runbooks/checksum-compat-multisite.md) に従い、新しい経路でも checksum を評価する。clab02 の helper は対象 IPv6 flag 未対応だが、k02／k03 の LB 試験で不正を検出せず、offload は `on`、state／timer は未作成。必要性を実測してから登録する。別ホスト clab01 の既存回避策は維持する。

## single-site から引き継ぐ調査

1. `TI-004`：Leaf uplink／Spine／peer-link の観測を追加し、Fabric 区間の遅延・欠落を hop ごとに分ける。複数 Leaf 経由の同一 flow と到着順も照合する。
2. `TI-004`：Pod netns の UDP socket drop とサーバ受信バッファを測定し、期限超過・socket drop・Fabric 欠落を別々に評価する。低レートから比較し、結果だけを理由に MTU や buffer を追加変更しない。
3. connectivity の累積 drop 検出と今回の増分を区別し、次回全体受入の判定条件を整理する。限定再試験の成功で全体結果を置き換えない。

課題の状態と終了条件は [試験課題台帳](test-issue-register.md#3-課題一覧) を参照する。
BGP 退避・障害系、経路途中の PMTUD、SNAT port 枯渇などの残りの受入は [構築計画](build-plan.md) で管理する。

## 合意済みの保留事項

- kernel 更新は multisite 試験後に検討する。checksum の回避策は暫定措置として維持する。
- 初期化の再現性は multisite の新規 Node に保存済み設定を適用して確認する。Node 再起動後のリンク復旧・設定維持は別の未検証事項として残す。
- multisite は k01 MetalLB の限定調査、k02／k03 導入と Mesh 基本通信を確認した。性能・障害・全体 connectivity の受入完了とはしない。
- single-site（clab01）Leaf の最新 MTU／LACP 変更の startup-config 保存は未実施。
  multisite（clab02）の BDC Leaf0101／0102 は保存済み。

初期化の受入範囲は [構築計画 3.2](build-plan.md#32-初期化の確認方法と-kernel-更新の時期2026-09-12-合意) を参照する。
