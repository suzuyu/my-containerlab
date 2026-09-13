# 2026-09-13 single-site 終了時確認と multisite 引継ぎ

## 判定と実施範囲

single-site は既知課題を残して一区切りとし、multisite の構築準備へ進める状態と判断する。
これは全体 connectivity・性能・冗長性の受入合格ではない。
2026-09-13 14:25 JST から clab01 の既存 `adc-k02` に対し、状態照合・既存 workload の DNS／低レート HTTP を確認した。
Node／Cilium／Fabric の再起動、設定投入、試験用 workload の追加、kernel 更新、`write memory` は行っていない。

## 終了時の結果

| 確認対象 | 結果 |
|---|---|
| 確認コマンド | 69 件すべて終了コード 0。下記の状態・応答も照合 |
| Node／Cilium | 3 Node Ready、Cilium 3/3。Fabric InternalIP を維持 |
| Tetragon／Hubble | Tetragon 3/3、Operator・Relay・UI 各 1 Ready。Hubble 接続 3/3 |
| BGP | 両 worker から 8 セッション Established。集約 blackhole route の check 成功 |
| Node MTU／LACP | eth1／eth2／bond／VLAN は 9150、管理 eth0 は 1500。bond の状態を証跡に保存 |
| Egress 初期化 | 専用 helper の check 成功、DaemonSet 2/2。既存 IP／checkpoint と対象 Node を維持 |
| CoreDNS | 保存済み resolver と Corefile の整合を確認。既存 Pod から内部 Service DNS と外部名の HTTP 成功 |
| checksum 回避策 | 登録 state の check 成功。既存 timer active、直近 service は Result=success／ExecMainStatus=0 |
| LB 通信 | Fabric client から Cluster／Local Service の IPv4／IPv6、各 10 回、計 40/40 HTTP 成功。両 backend の応答を確認 |
| 設定保存・配送 | topology、Cilium values／resources、Egress manifest、Leaf 4 台の保存 config の計 15 ファイルがローカルと実行ホストで同一 SHA256 |
| 証跡 | 実行ホストの結果をローカルへ転送し、SHA256SUMS の全ファイルを照合 |

Hubble CLI 1.19.4 と Relay 1.20.1 の版差による互換性警告は継続している。今回の接続は成功しており、版の変更は行っていない。
HTTP 成功は低レート・短時間の結果であり、TI-004 の遅延・再送・損失が解消したという判定には使用しない。

## 引き継ぐ既知課題と扱い

| 項目 | 状態・次の扱い |
|---|---|
| connectivity 全体 | 09-12 の 80/82 tests 成功を維持。旧 Pod IP 修正後の限定 6 actions 成功を全体合格へ置き換えない。累積 drop と増分の判定は次回全体受入へ引き継ぐ |
| TI-004 | Fabric 遅延・順序逆転・欠落区間と socket 未回収は原因未確定。既存測定を比較基準に保持し、性能受入前に再開 |
| TI-002 | Forwarding／ECMP 冗長性は未合格。multisite の経路・障害受入で区別して確認 |
| TI-006／Egress 追加試験 | 初回 timeout の原因、Node 障害、SNAT port 枯渇は保留。通常 multisite は Egress Gateway を無効化 |
| Leaf startup-config | 最新 MTU／LACP 変更の write memory は未実施。現 Leaf を再起動後も継続利用する場合は保存が必要。新規構築では照合済みの保存ファイルを使用 |
| kernel／初期化 | kernel 更新は multisite 試験後。新規 Node の初期化再現性は multisite 構築時に確認。Node 再起動後の復旧は別の未検証事項 |
| 証跡の残事項 | 過去の Tetragon 原本・転送元ハッシュの未照合は維持。今回の証跡照合で過去分を補完したとはしない |

## multisite の準備結果

[checksum 専用手順](../../../runbooks/checksum-compat-multisite.md) を作成し、次を整備した。

- 新しい k02／k03 の UID ごとに state・timer を分離する。
- Cilium bootstrap → 明示登録・適用 → timer → 常設設定の一括適用の順序とする。
- 一括 driver に `--checksum-state-k03` を追加し、k02 のオプションも multisite で使用可能にした。
- 両クラスタの登録 state と接続先 UID を最初の設定変更前に照合する。
- 各 Cilium 導入直後・DNS 設定前に checksum を再適用・確認する。

今回、multisite の deploy・初回登録・timer 作成・実適用は行っていない。
旧 single-site の timer は稼働中の Node を保護するため維持し、Node 名を再利用する実際の移行時に停止する。

## 証跡の所在

セッション：`singlesite-closeout-2026-09-13-142550`。
実行ホストのリポジトリとローカルの同一相対パスに保存した。

[終了時確認の証跡](../../../../../nxos_singlesite/operations/cilium-lab/2026-09-13/singlesite-closeout-2026-09-13-142550/) は Git 管理外。
`summary.json`、個別 check 出力、`source-hashes.json`、`SHA256SUMS` を保持する。
変更前提・全体受入の詳細は [09-12 の回帰結果](../2026-09-12/singlesite-regression-validation-2026-09-12.md) を参照する。
