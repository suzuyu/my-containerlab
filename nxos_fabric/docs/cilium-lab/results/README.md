# 実施結果・履歴

現在の進捗は [status](../status.md) を参照する。ここでは実施当時の条件と結果を保持する。
記録日をディレクトリ名とし、日付をまたぐ作業の実時刻は各文書に記載する。

| サイト・記録日 | 結果 |
|---|---|
| multisite / 2026-09-25 | [VIP／Egress 移行・k02 復帰](multisite/2026-09-25/upgrade-rehearsal.md)：同一 VIP、別／同一 Egress IP の往復を実施。時間目標は未達。復元の照合結果は本文を参照 |
| multisite / 2026-09-25 | [k04 の Cilium／3 クラスタ Mesh](multisite/2026-09-25/k04-clustermesh.md)：BGR 保存、Cilium／Tetragon 導入、full mesh、Pod／NodePort 各 48/48。初回の並列・短 timeout 条件での失敗は残課題 |
| multisite / 2026-09-25 | [k04 の追加](multisite/2026-09-25/k04-addition.md)：Kubernetes 1.36.4 の新規作成、Leaf 4 台の再作成と既存接続の復旧。Fabric 受入状況は記録本文を参照 |
| multisite / 2026-09-25 | [共存試験前の復旧・構築](multisite/2026-09-25/pre-coexistence-recovery.md)：両 BDC Leaf の member／MTU 復旧、k02／k03 の基盤・Mesh・基本通信を確認。startup-config 保存・照合済み。共存試験は別記録 |
| multisite / 2026-09-25 | [Egress／Mesh 共存の限定実験](multisite/2026-09-25/egress-clustermesh-coexistence.md)：両 AF の local SNAT・remote 非選択・Mesh／Global Service・API 障害分離を確認。Gateway 復帰時の Node アドレス／経路消失を TI-009 として記録 |
| multisite / 2026-09-25 | [別クラスタの Egress Gateway を利用できないことの確認試験](multisite/2026-09-25/remote-egress-gateway-negative-test.md)：両方向・両 AF で `Not Found`／`NO_EGRESS_GATEWAY`。対向 Gateway は選択できず、local 復帰で通信回復 |
| multisite / 2026-09-13 | [保存時点・終了確認](multisite/2026-09-13/checkpoint.md)：基盤と Mesh 接続の再確認、残課題、Git 保存範囲 |
| multisite / 2026-09-13 | [k03 導入・Cluster Mesh 接続と双方向通信](multisite/2026-09-13/k03-clustermesh-install.md)：Leaf MTU／Mesh 名前解決／更新方式の修正、Pod／Global Service／LB 確認 |
| multisite / 2026-09-13 | [k02 の初回導入・基本確認](multisite/2026-09-13/k02-initial-install.md)：Cilium／BGP／LB／Hubble／Tetragon、k03 接続は未実施 |
| multisite / 2026-09-13 | [k01 MetalLB の BGP 未確立・ARP／ND 調査](multisite/2026-09-13/k01-metallb-neighbor-investigation.md) |
| single-site / 2026-09-13 | [終了時確認・multisite 引継ぎ](singlesite/2026-09-13/singlesite-closeout-2026-09-13.md) |
| single-site / 2026-09-12 | [設定照合・全体回帰・性能切り分け](singlesite/2026-09-12/singlesite-regression-validation-2026-09-12.md)、[検証ステータス](singlesite/2026-09-12/validation-status-2026-09-12.md)、[Egress 初期化](singlesite/2026-09-12/egress-interface-init-validation-2026-09-12.md) |
| single-site / 2026-09-12 | [実行環境・作業履歴](singlesite/2026-09-12/execution-environment-history-2026-09-12.md)：整理前の環境メモ（09-06〜13） |
| single-site / 2026-09-06 | [検証ステータス](singlesite/2026-09-06/validation-status-2026-09-06.md)、[当時の概要・初期方針](singlesite/2026-09-06/lab-overview-2026-09-06.md)：整理前の README |
| single-site / 2026-08-30 | [検証ステータス](singlesite/2026-08-30/validation-status-2026-08-30.md) |

multisite の結果は実施後に `multisite/<YYYY-MM-DD>/` へ追加する。
生ログ・capture・ハッシュ台帳は Git 管理外の `operations/` に保持し、ここには条件・判定・証跡の所在を記載する。

[文書の入口へ戻る](../README.md)
