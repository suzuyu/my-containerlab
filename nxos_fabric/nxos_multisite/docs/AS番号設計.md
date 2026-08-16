## AS 番号表

nxos-fabric-multisite で使用する AS 番号を定義する

AS 番号を全て統一して動かすパターンと、DCI/Underlay/EVPN で全て変えるパターンの2パターンを作成する

## 1. AS 番号統一

| 項目 | Site A (ADC) | Site B (BDC) | Site C (CDC) | WAN (Underlay) | RouteServer (RS) |
| --- | --- | --- | --- | --- | --- |
| Site Local Fabric AS | 65001 | 65002 | None | None | None |
| Legacy/L3SW AS       | None  | None  | 65100 | None | None |
| DCI Underlay AS | 65001 | 65002 | 64903 | 64600 | 65000 |
| DCI EVPN AS | 65001 | 65002 | 64931 | None | 65000 |
| Underlay IP | 10.0.0.0/16 | 10.1.0.0/16 | 10.2.0.0/16 | 10.255.0.0/16 | None (WAN IP(10.255.0.0/16) Use) |

### 対応 Config

[AS番号統一configディレクトリ](../configs/as-equals/)

## 2. AS 番号不一致


| 項目 | Site A (ADC) | Site B (BDC) | Site C (CDC) | WAN (Underlay) | RouteServer (RS) |
| --- | --- | --- | --- | --- | --- |
| Site Local Fabric AS | 65001 | 65002 | None | None | None |
| Legacy/L3SW AS       | None  | None  | 65100 | None | None |
| DCI Underlay AS | 64601 | 64602 | 64603 | 64600 | 64699 |
| DCI EVPN AS | 64901 | 64911 | 64931 | None | 65000 |
| Underlay IP | 10.0.0.0/16 | 10.1.0.0/16 | 10.2.0.0/16 | 10.255.0.0/16 | None (WAN IP(10.255.0.0/16) Use) |

### 対応 Config

[AS番号不一致configディレクトリ](../configs/as-changes/)
