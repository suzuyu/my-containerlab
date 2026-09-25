# 共存試験前の k02／k03 復旧・構築記録

2026-09-25、clab02 上の再構築後の k02／k03 を確認し、通常の Cilium／Mesh 基盤の設定を完了した。
**両 BDC Leaf の復旧差分を承認後に適用し、Mesh 相互接続と双方向の基本通信を確認した。**
この復旧段階では Egress Gateway は両クラスタで無効を維持し、共存試験は未開始。
今回の Nexus 変更は当初 running-config のみとし、その後の追加依頼で両機の startup-config へ保存・照合した。
続けて実施した共存試験は [別記録](egress-clustermesh-coexistence.md)にまとめる。

## 完了状態

実測環境は Kubernetes `v1.35.5`、Cilium `1.20.1`、Tetragon `1.7.0`、
ホスト kernel `5.14.0-611.49.1.el9_7.x86_64`。

| 確認項目 | k02 | k03 |
|---|---|---|
| Node Ready／Fabric InternalIP | `3/3`、IPv4／IPv6 とも反映 | 同左 |
| Cilium／Tetragon DaemonSet | 各 `3/3` | 各 `3/3` |
| Mesh API／Tetragon operator | `2/2`／`1/1` | `2/2`／`1/1` |
| BGP | `8/8 Established` | `8/8 Established` |
| Mesh 接続 | agent `3/3`・KVStoreMesh `2/2` | agent `3/3`・KVStoreMesh `2/2` |
| Hubble | Healthcheck OK、Connected Nodes `6/6` | 同左 |
| 外部 LB／worker 間 NodePort HTTP | IPv4／IPv6、計 `12/12` | IPv4／IPv6、計 `12/12` |
| 外部観測点の IPv6 TCP 応答 checksum | correct `24`、不正 `0` | correct `26`、不正 `0` |

サイト間 Pod HTTP は、各サイトの両 worker から相手の両 worker へ IPv4／IPv6 で確認し `16/16` 成功。
Global Service は両サイトに同名 Service を置き、`affinity: remote` で相手サイトの応答を検証し `8/8` 成功した。
これは基本通信の確認であり、local 優先からの fallback や障害受入の代替ではない。
Mesh API Service は両クラスタとも `sessionAffinity: ClientIP`、PDB は `minAvailable: 1`。
Helm values で Egress Gateway、CiliumEndpointSlice、BPF masquerade がすべて `false` であることを確認した。

## 開始状態と実施内容

- kind の 6 Node は約 4 日前の作成、Cilium `1.20.1` は当日の初回 install 済み。
- Kubernetes の InternalIP は 6 台とも管理側 `172.18.*`。Fabric 側の bond／VLAN と IP は存在した。
- 6 台の kubelet を既存 helper で Fabric IPv4／IPv6 へ修正し、Node Ready と IP 更新を順に確認した。
- CiliumNode は旧管理 IP を保持していたため、クラスタごとに Cilium DaemonSet を rolling restart し、Fabric IP 反映を確認した。
- k02／k03 の CA fingerprint は一致。CA の置換は行っていない。
- Node preflight は両クラスタとも `PASS=78 WARN=0 FAIL=0` を確認した。ただしこの検査は Leaf の LACP／MTU を含まない。
- k02 の通常 values、CoreDNS、LB／BGP、Mesh API Service、Tetragon を適用した。k03 は Leaf 復旧後に残りを完了した。
- k02 は Cilium／Tetragon 各 `3/3`、Tetragon operator `1/1`。外部 LB／worker 間 NodePort の IPv4／IPv6 HTTP は各 3 回、計 `12/12` 成功した。
- 外部観測点へ到着した IPv6 TCP 応答は checksum correct `24` packet、不正 `0`。送信側で採取した TX offload 前の表示はこの受信判定に混ぜていない。
- k03 は Cilium values の適用後、DNS 確認で API→kubelet の TLS が止まったため一旦停止した。復旧後は上流 DNS への直接問い合わせと CoreDNS 経由の名前解決が成功した。
- checksum 回避策の state／timer は新規作成せず、Egress／MCS／WireGuard は有効化していない。

## k02 の BGP 隣接

初回は worker2 → BGR01 の IPv4／IPv6 が `active`、ARP／ND が `INCOMPLETE` だった。
BGR01 から対象 Node への限定 ping 後に解決し、BGP は `8/8 Established` となった。
前回と同じ初期隣接の課題として残す。逆方向 ping は今回の復旧操作であり、恒久対処や無介入の初期化再現性の合格ではない。
この k02 の隣接復旧では Nexus の設定変更・BGP clear は行っていない。

## k03 の停止原因と復旧差分

両 BDC Leaf で次を確認した。

| 対象 | 稼働状態 | 保存設計 |
|---|---|---|
| `Po14`～`Po16` | MTU `9216`、trunk、vPC 設定あり。ただし down・member なし | 対応する物理ポートを LACP member として収容 |
| `Ethernet1/4`～`1/6` | `channel-group` なし、実効 MTU `1500` | 各々 `Po14`／`Po15`／`Po16`、`mode active` |
| Node 間 TLS | TCP 開始後、`1546` byte の ClientHello で timeout | API→kubelet の応答と Pod exec が成功 |

Po の MTU だけでは状態を判定できない。物理 member と実転送まで照合する必要がある。
[復旧 Config](../../../../../nxos_multisite/configs/changes/cilium-k03-recovery-20260925/README.md)を、ユーザー承認後に
Leaf0101 → Leaf0102 の順で running-config へ適用した。対象は各 `Ethernet1/4`～`1/6` の
MTU `9216`、対応する `Po14`～`Po16` への LACP `mode active` 加入と `no shutdown`。
初回は保存せず、追加依頼後に両機で `copy running-config startup-config` を実行し、対象物理ポートと Po の保存内容を照合した。

両機で対象 Po が `SU`、物理 member が `P`、MTU `9216`、vPC consistency success を確認した。
Leaf0102 の適用直後は一部が LACP 収束待ちだったが、再確認時はすべて up。
k03 の 3 Node で bond 両 member が同じ aggregator に参加した。
API Node から両 worker の kubelet への TLS 接続は HTTP `401` まで到達し、API 経由の Pod exec も成功した。
`401` は未認証の直接アクセスへの応答であり、認証済み health check の合格という意味ではない。

k03 の残設定後は KVStoreMesh が先に接続し、agent は一時的に remote configuration 待ちだった。
追加の restart は行わず、その後の確認で両サイトとも agent `3/3`・KVStoreMesh `2/2` に収束した。
k03 の BGP は設定後に `8/8 Established` となり、k03 では逆方向 ping による介入は不要だった。

## 通信確認の範囲

一時 namespace `cilium-pre-coex-0925` に各 worker 固定の HTTP Pod と dual-stack Service を作成した。
外部観測点は ADC の `t1sv0101`。LB と worker1 の NodePort は worker2 のみを backend とし、
Node 間の返り経路を含めて各 AF・各宛先を 3 回ずつ確認した。
k03 の checksum は観測点の受信方向に限定して採取し、`26` packet が correct、capture drop は `0`。
この限定経路の結果を全経路・負荷条件での checksum 保証とはしない。
一時リソースは確認後に両クラスタから撤去済み。撤去後も Mesh agent `3/3`・KVStoreMesh `2/2`、
BGP 各 `8/8 Established` を確認し、両クラスタの CA fingerprint も一致した。

## 手順とスクリプトの修正

- k02 README のパターン B に、環境設定、Node IP 修正、Cilium／CA、条件付き checksum 登録、常設設定、完成状態確認を集約した。
- k03 README のパターン B は共通手順へ案内し、相反するコマンドの重複を除いた。
- 一括 driver と checksum bootstrap は、相手サイト完成前に Mesh 全体の `status --wait` を待たず、ローカルの rollout を確認する。
  全体 status と Mesh 接続は両サイト完成後に確認する。
- context／経路の存在確認で `grep -q` が先に終了すると、`pipefail` により上流の SIGPIPE が欠落と誤判定され得るため、最後まで読み取る処理へ修正した。
- IPv6 経路欠落という初期判定は、保存した変更前の経路出力から誤判定と訂正した。k03-worker2 には同一経路の `replace` を一度実行したが、実際の値は変更していない。
- CoreDNS の Pod exec にはリクエストのタイムアウトを追加した。

## 証跡と残作業

変更した driver の分離テストは `11/11` 成功。導入途中の Mesh 待ち、ローカル rollout 失敗、
長い context 出力の SIGPIPE を確認した。README／runbook／Config README の shell ブロックとリンクを静的検査した。
公開 Config は `140` ファイルのサニタイズ検査に成功。今回の復旧 Config `2` ファイルに認証行・global IP・管理設定の追加はない。
既存の lab 用管理設定 `530` 件は変更していない。

生ログ・変更前 values・一時 manifest は Git 管理外の
`nxos_fabric/nxos_multisite/operations/cilium-lab/2026-09-25/pre-coexistence/` に保持する。
認証情報と raw config は公開文書へ転載しない。

基盤復旧と最小通信確認を完了した。今回の BDC Leaf 差分は startup-config へ保存・照合済み。再起動試験は未実施。
既存計画の通常・障害受入と `COEX-00`～`COEX-11` は別に実施・判定する。
次の順序と開始条件は [共存試験計画](../../../tests/egress-clustermesh-coexistence-test.md)と
[アップグレード前の先行試験](../../../design/clustermesh-cluster-upgrade-design.md#upgrade-prerequisites)に従う。
