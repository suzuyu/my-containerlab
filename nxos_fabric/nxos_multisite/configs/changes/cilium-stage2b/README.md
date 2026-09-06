# Egress 常設設定への移行と確認

## 目的と位置付け

このディレクトリは、旧環境を基本 config に揃えるための移行差分である。試験ごとに追加・撤去する設定ではない。
基本 config に Egress の受信許可・集約・公開範囲の制御を含める。停止中の環境は基本 config を使用して起動し、差分だけの二重投入は不要。
[経路設計](../../../../docs/cilium-lab/egress-gateway-routed-design.md)を正本とする。

- Cilium Node は所有する `/32`・`/128` を広報する。
- NX-OS は Egress 範囲の `/24`・`/64` を集約する。現段階では `summary-only` を指定せず、個別経路も広報する。経路数の削減は未実施。
- Leaf の Egress 専用 import 除外は両 family とも削除し、既存 import 条件に従う。
- Egress 経路は LB と同じ広報方針とし、Egress 専用の `no-export` を付けない。
- Node IP／Cilium advertisement／Egress Policy の有無と、NX-OS の常設設定を分けて管理する。

## 対象と適用順

| 順序 | 対象 | 差分 | 主な変更 |
|---|---|---|---|
| 1 | `adc-lfsw0101` | [adc-lfsw0101.cfg](adc-lfsw0101.cfg) | Egress 専用追加設定なし（旧設定は移行差分で撤去） |
| 1 | `adc-lfsw0102` | [adc-lfsw0102.cfg](adc-lfsw0102.cfg) | Egress 専用追加設定なし（旧設定は移行差分で撤去） |
| 1 | `adc-lfsw0103` | [adc-lfsw0103.cfg](adc-lfsw0103.cfg) | Egress 専用追加設定なし（旧設定は移行差分で撤去） |
| 1 | `adc-lfsw0104` | [adc-lfsw0104.cfg](adc-lfsw0104.cfg) | Egress 専用追加設定なし（旧設定は移行差分で撤去） |
| 2 | `adc-bgrt0101` | [adc-bgrt0101.cfg](adc-bgrt0101.cfg) | k02 IPv4 `/24 le 32`・IPv6 `/64 le 128` の permit 30、`172.16.24.0/24`／`fd21:0:0:24::/64` 集約 |
| 2 | `adc-bgrt0102` | [adc-bgrt0102.cfg](adc-bgrt0102.cfg) | k02 IPv4 `/24 le 32`・IPv6 `/64 le 128` の permit 30、`172.16.24.0/24`／`fd21:0:0:24::/64` 集約 |
| 3 | `bdc-lfsw0101` | [bdc-lfsw0101.cfg](bdc-lfsw0101.cfg) | k03 BGP 基盤、受信 filter、`172.16.25.0/24`／`fd21:0:0:25::/64` 集約、公開範囲制御 |
| 3 | `bdc-lfsw0102` | [bdc-lfsw0102.cfg](bdc-lfsw0102.cfg) | k03 BGP 基盤、受信 filter、`172.16.25.0/24`／`fd21:0:0:25::/64` 集約、公開範囲制御 |

BDC 差分は Egress permit だけでなく、未反映だった `loopback105`、worker 2 台 × 2 family の eBGP multihop、
`local-as 65020 no-prepend replace-as`、LB filter、ECMP を含む。Fabric ASN `65002` は維持する。
専用 loopback の direct redistribution は、endpoint だけに no-export を付ける route-map へ変更し、その他の connected route は従来どおり扱う。

`as-equals` を変更元とし、`scripts/generate_as_changes.py` で `as-changes` を生成する。
multisite は停止中のため、この変更の parser・session・datapath・DCI advertised-routes は未確認である。

## 適用前の確認

対象機器の該当 route-map／prefix-list と BGP・経路を保存する。今回追加する名前、permit 30 が
別用途で使われている場合は上書きしない。既存 inbound route-map がある場合も統合内容を確認する。

ADC BGR：

```text
show route-map CILIUM_K02_IN_V4
show route-map CILIUM_K02_IN_V6
show ip prefix-list CILIUM_K02_EGRESS_V4
show ipv6 prefix-list CILIUM_K02_EGRESS_V6
show running-config | include aggregate-address
show bgp vrf tenant1-vpc1 ipv4 unicast summary
show bgp vrf tenant1-vpc1 ipv6 unicast summary
```

Leaf：

```text
show route-map IPv4_IMPORT_MAP_controller-vpc1
show route-map IPv6_IMPORT_MAP_controller-vpc1
show running-config | include CILIUM_EGRESS_SITE_ONLY
```

BDC では追加で `show interface loopback105`、`show route-map CILIUM_K03_IN_V4`／`V6`、
`show route-map CILIUM_K03_DIRECT_V4`／`V6` を確認する。

## 旧 Egress no-export 設定からの移行

以前の設定を投入済みの場合だけ、[Leaf 0101 の撤去差分](adc-lfsw0101-remove-egress-no-export.cfg) と
[Leaf 0102 の撤去差分](adc-lfsw0102-remove-egress-no-export.cfg) を対応する機器へ適用する。
neighbor の参照を外してから専用 route-map を削除する。上記 `show running-config` で対象の定義・参照がなくなることを確認する。
新しい基本 config から構築した環境では、この撤去差分は不要。
BDC は今回の旧設定が未投入である。修正済みの基本 config／通常差分を使用する。
k03 の接続用 loopback に付ける no-export は Egress IP の制御ではないため維持する。

## IPv4 filter 簡略化への移行

k02 IPv4 の受信許可を `172.16.24.0/24 le 32` に統合し、Leaf の `CILIUM_EGRESS_SCOPE_V4` と
`IPv4_IMPORT_MAP_controller-vpc1 deny 5` を削除する。この差分は前回の IPv4 変更用であり、最新化には下記の IPv6・k03 移行も実施する。
旧設定を投入済みの機器だけ、対応する `<device>-simplify-egress-v4.cfg` を適用する。
BGR 差分は sequence 5 で新しい許可を先に追加し、旧 sequence 10／20 を削除する。sequence 5 を常設行として残す。
新しい基本 config から構築する場合、この移行差分は不要。

## IPv6・k03 の範囲統一と記載順

k02 IPv6 は `fd21:0:0:24::/64 le 128`、k03 IPv4 は `172.16.25.0/24 le 32`、
k03 IPv6 は `fd21:0:0:25::/64 le 128` の 1 行に統合する。各 prefix-list の sequence は 5 とする。
Leaf の `CILIUM_EGRESS_SCOPE_V6` と `IPv6_IMPORT_MAP_controller-vpc1 deny 5` を削除する。
旧設定を投入済みの場合だけ、各機器の `<device>-unify-egress-ranges.cfg` を適用する。
旧 IPv4 除外も残る環境では、前節の `*-simplify-egress-v4.cfg` を先に適用する。
BGR／BDC Leaf は新しい範囲を sequence 5 に追加してから旧 sequence 10／20 を削除する。

基本 config と通常差分の route-map は、同じ名前ごとに sequence 昇順でまとめる。
`CILIUM_K02_IN_V4/V6`／`CILIUM_K03_IN_V4/V6` は permit 10 → 20 → 30 の順になる。
装置上の評価順は sequence で決まるため、並べ替えだけのために route-map を削除・再作成しない。
ADC Leaf の通常 `.cfg` は追加設定がなく、旧設定を撤去する移行差分だけが必要となる。

## 適用と受入確認

1. 適用順に沿って各 `.cfg` を 1 台ずつ適用し、parser error がないことを確認する。
2. 既存 BGP session と LB 経路を比較する。hard clear は行わない。
3. [single-site 手順 7](../../../../docs/cilium-lab/egress-gateway-test-plan.md#egress-routed-setup)で Node IP と Cilium advertisement を準備する。
4. Node の advertised-routes は個別経路、NX-OS は個別経路と集約の両方を持つことを確認する。
5. controller VRF で両 family の Egress 集約について既存 import 条件の動作を確認し、全撤回後に経路が消えることを確認する。tenant BGP の Egress 経路に no-export が付かないことも確認する。
6. multisite 起動後は LB と比較し、BGW の DCI peer advertised-routes と対向 site の tenant RIB に Egress 範囲が届くことを実測する。prefix 許可リストを導入する場合は Egress も含める。
7. contributor を全撤去すると個別経路と集約が消え、LB 経路が維持されることを確認する。
8. 受入後、常設設定を `copy running-config startup-config` で保存し、startup の該当行を確認する。

k02 の照会例（k03 は `.24` → `.25`、IPv6 `:24:` → `:25:`）：

```text
show ip route 172.16.24.0/24 vrf tenant1-vpc1
show ipv6 route fd21:0:0:24::/64 vrf tenant1-vpc1
show ip route 172.16.24.1/32 vrf tenant1-vpc1
show ip route 172.16.24.2/32 vrf tenant1-vpc1
show ipv6 route fd21:0:0:24::1/128 vrf tenant1-vpc1
show ipv6 route fd21:0:0:24::2/128 vrf tenant1-vpc1
show ip route 172.16.24.0/24 vrf controller-vpc1
show ipv6 route fd21:0:0:24::/64 vrf controller-vpc1
show bgp vrf tenant1-vpc1 ipv4 unicast 172.16.24.0/24
show bgp vrf tenant1-vpc1 ipv6 unicast fd21:0:0:24::/64
```

個別経路の最終 next-hop は各 IP の所有 Node に一致させる。集約 discard は未割当宛先を処理するもので、
存在する `/32`・`/128` の転送に使われないことを確認する。片系障害で個別経路を失った終端へ集約宛の通信が入る場合を
別途検証するまで、`summary-only` は有効にしない。

## 復旧

通常の試験終了では Policy → Cilium advertisement → Node IP の順に撤去する。**NX-OS の常設設定は残す。**
集約コマンドが残っていても、全 contributor の撤回後は動的な集約経路が消えることを確認する。

`*-rollback.cfg` は基盤設定そのものを撤去するためのファイルで、通常の試験後片付けでは使わない。
BGR／BDC Leaf の Egress 集約と permit 30／専用 prefix-list だけを撤去し、既存 LB 設定や k03 の BGP 基盤は残す。
Leaf の Egress 専用 import 除外は両 family とも撤去済みであり、再追加しない。移行全体を取り消す場合は、保存した変更前設定を基に復元する。
