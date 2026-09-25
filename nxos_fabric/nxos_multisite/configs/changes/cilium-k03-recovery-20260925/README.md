# k03 再構築後の BDC Leaf member 復旧案

状態：2026-09-25、ユーザー承認後に **両機の running-config へ適用済み**。続けてユーザー承認を受け、startup-config へも保存・照合済み。対象は `bdc-lfsw0101`／`bdc-lfsw0102` の k03 専用 `Ethernet1/4`～`1/6`。

両機の `Po14`～`Po16` は trunk／MTU `9216`／vPC 設定済みだが、物理 member の `channel-group` が欠落していた。
物理側は MTU `1500`、Po は down・member なし。k03 の Node 間 TCP 接続は開始するが、
`1546` byte の TLS ClientHello 後に timeout し、API 経由の Pod exec が進まない。
保存設計と稼働設定の差分であり、Cilium Egress／Mesh 共存の不具合とは判定しない。

| Config | 復旧する収容 |
|---|---|
| [bdc-lfsw0101.cfg](bdc-lfsw0101.cfg) | `Ethernet1/4` → `Po14`、`1/5` → `Po15`、`1/6` → `Po16` |
| [bdc-lfsw0102.cfg](bdc-lfsw0102.cfg) | 同上。各 k03 Node のもう一方のリンク |

各物理ポートを既存 Po と同じ MTU `9216` に揃え、保存設計の LACP `mode active` で加入させる。
`force` で互換性確認を省略しない。エラー時は後続ポート・対向機へ進まず原因を確認する。
適用時は Node の両リンクと vPC peer の状態を確認し、片機ずつ実施する。member の加入に伴う通信断を見込む。
今回の適用はユーザー承認後に Leaf0101 → Leaf0102 の順で実施した。初回適用では保存せず、追加の保存依頼後に両機で `copy running-config startup-config` を実行した。

確認コマンドは両機で実施する。

```text
show port-channel summary
show interface ethernet1/4 | include MTU
show interface ethernet1/5 | include MTU
show interface ethernet1/6 | include MTU
show interface port-channel14 | include MTU
show interface port-channel15 | include MTU
show interface port-channel16 | include MTU
show vpc brief
```

期待値は `Po14`～`Po16` が `SU`、各 member が `P`、物理・Po MTU が `9216`、vPC consistency が success。
Node の bond 両 member、Fabric InternalIP、API→kubelet TLS、Pod exec／DNS、BGP／Mesh を続けて確認する。
LACP の表示だけを通信復旧の合格としない。

今回の差分を戻す場合は、各物理ポートの追加した `channel-group` を解除し MTU `1500` に戻す。
これは変更前の不具合状態への復帰なので、正常化手段とは扱わない。既存 Po／vPC／VLAN は削除しない。
実機ログ・認証情報は本ディレクトリへ含めない。

## 適用結果

両機で `Po14`～`Po16` の `SU`、各 member の `P`、物理 MTU `9216`、vPC consistency success を確認した。
Leaf0102 の投入直後には LACP の収束待ちで一部が down だったが、再確認時に 3 本とも up になった。
k03 の 3 Node は bond 両 member が同じ aggregator に参加し、API→両 worker の kubelet TLS と Pod exec が復旧した。
操作と確認の記録は [共存試験前の復旧結果](../../../../docs/cilium-lab/results/multisite/2026-09-25/pre-coexistence-recovery.md) を参照する。

両機で保存コマンドの `Copy complete` と、startup-config の物理ポートの MTU／channel-group、Po の MTU／vPC を照合済み。装置再起動による再現試験は行っていない。
