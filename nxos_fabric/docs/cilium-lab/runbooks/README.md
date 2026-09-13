# 準備・運用手順

実行環境と共通の操作手順。試験ごとの操作は [tests](../tests/README.md) を参照する。

| 文書 | 内容 |
|---|---|
| [bgp-maintenance-and-route-drain.md](bgp-maintenance-and-route-drain.md) | Cilium BGP 経路退避とメンテナンス設計 |
| [checksum-compat-operations.md](checksum-compat-operations.md) | VXLAN checksum 互換設定の登録・再適用・監視 |
| [checksum-compat-multisite.md](checksum-compat-multisite.md) | multisite のクラスタ別登録・監視と一括再適用 |
| [client-tools.md](client-tools.md) | Fabric 側 Kubernetes client と CLI 準備 |
| [execution-environment-singlesite-k02.md](execution-environment-singlesite-k02.md) | 実際の試験環境：single-site k02 |
| [kernel-compatibility-policy.md](kernel-compatibility-policy.md) | Cilium 導入前の kernel 判定と IPv6 checksum 対応方針 |
| [resource-and-preflight.md](resource-and-preflight.md) | リソース設計と Kernel／Kind Node preflight |

[文書の入口へ戻る](../README.md)
