# Egress Gateway／Cluster Mesh 共存の限定実験

2026-09-25、clab02 の `adc-k02`／`bdc-k03` で実施した。
ユーザー依頼に従い、先に両 BDC Leaf の復旧設定を startup-config へ保存・照合した。
[復旧記録](pre-coexistence-recovery.md)に続く試験である。

## 実施範囲と判定

**判定は `Partial`。通常時の共存通信と障害分離は成功したが、Gateway の無介入復帰は未合格。**
通常 Cilium values へ戻し、変更前との一致と通信回帰を確認した。

Stage 5 のサイト断、VXLAN-only 断、全体 connectivity、MTU／性能等の全受入は未完了。
今回は復旧後の基準通信を確認し、ユーザーの共存試験続行依頼に基づく限定実験として先行した。
元の計画にある「Stage 5 全体合格」を達成した扱いにはしない。
本結果だけでクラスタアップグレードや Egress IP 移管の開始条件をすべて満たしたとは判定しない。

公式文書は Egress Gateway と Cluster Mesh を非互換としている。
以下の結果は本ラボで観測した動作であり、公式サポートへの昇格を意味しない。
参照：[Cilium Egress Gateway の制約](https://docs.cilium.io/en/stable/network/egress-gateway/egress-gateway/#incompatibility-with-other-features)。
参照時の stable 文書は `1.20.2`、実測の Cilium は `1.20.1`。

## 構成と変更

| 項目 | k02 | k03 |
|---|---|---|
| Kubernetes／Cilium／Tetragon | `1.35.5`／`1.20.1`／`1.7.0` | 同左 |
| Gateway | `adc-k02-worker` | `bdc-k03-worker` |
| selected Pod | `smoke-worker2`、worker2 配置 | 同左 |
| control Pod | `smoke-worker`、worker 配置 | 同左 |
| Egress IPv4 | `172.16.24.1` | `172.16.25.1` |
| Egress IPv6 | `fd21:0:0:24::1` | `fd21:0:0:25::1` |
| 外部観測点 | ADC `t1sv0101` | BDC `t1sv0104` |
| 観測点アドレス | `172.16.0.1`／`fd21:0:0:1::101` | `172.16.0.4`／`fd21:0:0:1::104` |

ホスト kernel は `5.14.0-611.49.1.el9_7.x86_64`。
観測点は各サイト内に配置し、専用 nginx の `8088/TCP` 応答と access log に送信元 IP・試験 ID を記録した。
Egress Policy は IPv4／IPv6 別の計 4 個で、同一 namespace・同一 Pod label を選択し、
各サイトの観測点 `/32`／`/128` だけを宛先とする。
Gateway は site-local の `kubernetes.io/hostname` で指定し、`egressIP` を明示した。
試験のための Node label 追加は行っていない。

全稼働 kind Node と LB pool を照合し、予約 IP の競合がないことを確認した。
既存 helper で両 worker の `egress0` に `.1`／`.2`、`::1`／`::2` を作成した。
Interface 広告の `/32`／`/128` は各所有 Node を指し、全 4 worker の送信元 IP 指定 HTTP が両 AF で成功した。
ADC BGR／BDC Leaf の Egress 受信許可・集約は既に存在し、Nexus の追加投入は不要だった。

変更前の完全な Helm values を保存し、実験 overlay と復帰用の両 manifest を render した。
`cilium-config` の差分は `enable-egress-gateway: true` の追加と BPF masquerade の有効化。
`kubeProxyReplacement: true`、`identityAllocationMode: crd`、CES 無効は維持した。
k02 のみ有効化・検証後に k03 を有効化した。通常の `multisite-final` は変更していない。

## 通常時の結果

| Test ID | 実測 |
|---|---|
| `COEX-00` | 変更前の Egress map は全 6 Agent で未作成。両クラスタの status／Mesh／BGP／Hubble は正常。Pod HTTP `16/16`、Global Service `8/8` |
| `COEX-01` | k02 のみ有効化し、Agent／Operator rollout と Mesh agent `3/3`・KVStoreMesh `2/2` の接続を確認 |
| `COEX-02` | k02 selected Pod は両 AF とも専用 Egress IP。各 3 回、`6/6` 成功 |
| `COEX-03` | k03 も有効化し、両クラスタの Cilium／Mesh／BGP／Hubble が正常 |
| `COEX-04` | 両有効時の selected Pod は両クラスタ・両 AF で専用 Egress IP。計 `12/12` 成功 |
| `COEX-05` | 両クラスタの control Pod は Node IP で送信し、専用 Egress IP に変換されない。計 `12/12` 成功 |
| `COEX-06` | 全 `6/6` Agent の Egress map の source は自クラスタの selected Pod IPv4／IPv6 のみ。対向の同一 label Pod は非選択 |
| `COEX-07` | 両方向・両 worker・両 AF の Pod HTTP `16/16` 成功 |
| `COEX-08` | remote affinity の Global Service HTTP `8/8`。DNS 名で local 優先と local endpoint 除外時の remote fallback を両クラスタ・両 AF で確認し、追加 `8/8` 成功 |

MCS は未採用のため追加していない。IPv6 map の Gateway IP に IPv4 Node IP が現れるのは、
今回の VXLAN 終端が IPv4 であることと区別する。Gateway 上の Egress IP と外部で見える SNAT IPv6 を照合した。
Hubble では cluster／node 名を含む転送 flow を採取した。

Gateway 復旧後には各クラスタで新規 selected Pod を作成し、container 起動直後から各 AF 10 回ずつ送信した。
計 `40/40` が専用 Egress IP で成功した。今回の 2 Pod で初回から成功した結果であり、
公式に記載される Policy 適用遅延がないことの保証や、既存 `TI-006` の解決とはしない。
IP 制限が厳しいアプリでは、map と外部 probe の確認後に業務送信を開始する方針を維持する。

## 障害と復旧

`COEX-09` は k03 の Mesh API Deployment を `2 → 0 → 2` replica とし、DCI・Kubernetes API を維持した。
停止中も両クラスタの selected／control Pod の IPv4／IPv6 通信 `24/24` が成功した。
短時間の停止では k02 の Mesh CLI が connected を表示し続けたため、追加の同期試験を行った。

追加試験では API replica が `0` の間に新規 TCP 接続が失敗することを確認した。
k03 に新規 `sync-marker` Pod を作ると、停止中は k02 の ipcache に現れず、API 復旧後に現れた。
この停止中も外部 HTTP `24/24` が成功した。API 復旧後は両クラスタの Mesh 再接続を確認し、marker を撤去した。
CLI の cached 状態をもって新規同期が正常だとは判定しない。長時間断の TTL／stale state 評価は別の残項目とする。

`COEX-10` は k02 Gateway の `bond0.14` を一時的に down にした。
k02 の selected Pod は両 AF で timeout、同じ worker2 上に追加した control Pod は Node IP で継続し、
k03 selected Pod も両 AF の Egress IP で継続した。障害中の期待結果は `6/6`。
Gateway 自身に載る Pod の停止まで「選択通信だけの影響」とは扱わないため、control を健全な worker2 に分離した。

**link up だけでは復帰しなかった。** Gateway の Fabric IPv6 アドレスと、
`172.16.0.0/16`／`fd21:0:0::/48` の静的経路が消失していた。
直後の回帰では k02 が `0/12`、k03 が `12/12` であり、この失敗を後続の成功で上書きしない。
元の `fd21:0:0:4::2:1/64` と両静的経路を再設定して復旧した。
手動復元直後は `21/24` で、Gateway 上の control Pod の IPv6 が `0/3` だった。
その後の収束確認では `24/24` に戻った。途中の失敗を消さず、無介入・即時復帰とは区別する。
これは Node の interface down/up 後の構成復元課題として扱い、Cilium／Mesh の非互換が原因とは断定しない。
Gateway の無介入復帰は未合格で、将来の障害試験では link 状態に加えてアドレス・経路も復元対象とする。

次は Node の Fabric 初期化処理が link 復帰後にも保存設計を再反映する方法を検討し、
アドレス・経路・BGP・外部 probe の順で復帰を再試験する。IPv6 アドレス保持だけを変更しても、
今回消失した静的経路の復元まで確認したことにはならない。

試験中の停止条件に該当する remote 誤選択や制御通信の Policy 対象化は観測しなかった。
`COEX-10` の故障注入前には control Pod の manifest に Kubernetes 自動挿入 volume の参照が残り、
API の検証で拒否された。障害投入前に image／command のみの独立 Pod 定義へ修正してから実行した。

## 通常構成への復帰

`COEX-11` では専用 Policy 4 個を削除し、全 6 Agent の Egress map 消去を確認後、
試験用 Interface 広告 4 個を撤去した。
ADC BGR 2 台・BDC Leaf 2 台で各 Egress 個別経路と集約の計 `24` lookup が `Route not found` となることを確認し、
今回作成した全 4 worker の `egress0` を撤去した。NX-OS の常設受信許可・集約設定は維持した。

両クラスタを順に変更前の完全な values で Helm upgrade し、保存前後の Helm values と
`cilium-config` の data がともに完全一致した。Egress Gateway／BPF masquerade は `false`。
rollback 後は以下がすべて成功した。

| 回帰項目 | 結果 |
|---|---|
| サイト間 Pod HTTP | `16/16` |
| remote affinity の Global Service | `8/8` |
| DNS 名での local 優先／remote fallback | `8/8` |
| 両クラスタの外部 LB／worker 間 NodePort | `24/24` |
| 通常の Node IP に戻った外部 HTTP | `24/24` |

Egress Policy 用 CRD の登録は残るが、Policy オブジェクトは空。通常 profile への Egress 有効化は含めない。
一時 namespace は両クラスタから撤去し、専用 nginx の `8088/TCP` 待受も両観測点で停止した。
撤去後の最終確認は両クラスタとも 3 Node Ready、Cilium／Tetragon 各 `3/3`、Mesh API `2/2`、
Mesh agent `3/3`・KVStoreMesh `2/2`、BGP 各 `8/8 Established`、Hubble `6/6`。
Egress map は空または未作成であり、通常基盤へ復帰済み。

## 追加の制約確認

ユーザー依頼により [別クラスタの Egress Gateway を利用できないことの確認試験](remote-egress-gateway-negative-test.md)を別途実施した。
両方向・両 AF で標準 Policy は対向 Gateway を選択できず、`NO_EGRESS_GATEWAY` を確認した。
これは本書の local 共存試験と区別し、本書の `Partial` 判定および `TI-009` は維持する。

## 証跡

完全な values、Policy、試験 manifest、Node／Pod 配置、外部 access log、BPF map、Hubble flow、
NX-OS 経路、復旧記録は Git 管理外の
`nxos_fabric/nxos_multisite/operations/cilium-lab/2026-09-25/coexistence/` に保存する。
raw config・認証情報・実機ログを本文や公開 Config に転載しない。
