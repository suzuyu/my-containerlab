# Cilium ラボ文書

`nxos_singlesite`／`nxos_multisite` の Cilium 検証に使う設計、手順、試験結果をまとめる。

## 最初に読む文書

| 文書 | 確認すること |
|---|---|
| [現在のステータス](status.md) | 直近の結果、残課題、次の作業、保留事項 |
| [構成設計と構成図](architecture.md) | 通信経路、責務、MTU の現行設計 |
| [段階的な構築計画](build-plan.md) | Stage の順序、受入条件、チェックリスト |
| [試験課題台帳](test-issue-register.md) | TI ごとの状態、原因、回避策、終了条件 |

## 目的別の入口

| ディレクトリ | 内容 |
|---|---|
| [design/](design/README.md) | 要件、パラメータ・アドレス台帳、BGP、Egress、Cluster Mesh の詳細設計 |
| [runbooks/](runbooks/README.md) | 実行環境、事前確認、ツール準備、互換性対処、BGP 保守 |
| [tests/](tests/README.md) | ワークロードと試験手順。Network Policy／Tetragon、Egress の目的別手順 |
| [results/](results/README.md) | サイト・日付別の実施結果と過去の状態 |
| [reference/](reference/README.md) | 外部資料、調査資料、成果物一覧、CLI パッチと再現手順 |
| [images/](images/) | 文書で使う構成図 |

## 更新先のルール

- 現行設計は `architecture.md` と `design/`、現在の進捗は `status.md`、課題の詳細は `test-issue-register.md` を更新する。
- 構築順序・受入条件は `build-plan.md`、操作方法は `runbooks/` と `tests/` を更新する。
- 実施結果は `results/<site>/<YYYY-MM-DD>/` へ追加し、`status.md` からリンクする。日付をまたぐ継続試験は記録日を維持し、実施日時を本文に記載する。
- 過去の結果を現在値へ書き換えない。判定の訂正は理由と後続結果を追記し、当時の条件を残す。
- 生ログ・capture・認証情報は文書へ転載せず、Git 管理外の `operations/` に保持する。
- 移動・分割時は Test ID、課題 ID、参照先を維持する。今回の対応は [文書の移動・分割一覧](reference/document-map.md) を参照する。
