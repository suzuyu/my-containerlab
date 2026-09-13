# 実施結果・履歴

現在の進捗は [status](../status.md) を参照する。ここでは実施当時の条件と結果を保持する。
記録日をディレクトリ名とし、日付をまたぐ作業の実時刻は各文書に記載する。

| サイト・記録日 | 結果 |
|---|---|
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
