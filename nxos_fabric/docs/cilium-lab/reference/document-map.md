# 文書の移動・分割一覧（2026-09-13）

## 整理の方針

直下は `README.md`、`status.md`、`architecture.md`、`build-plan.md`、`test-issue-register.md` の 5 文書とする。
詳細設計・運用・試験・結果・参照資料を目的別に配置し、実施履歴は保持する。
相対リンクとリポジトリ内の文書パス参照を更新する。Test ID、TI ID、試験手順の節番号は変更しない。

## 旧パスからの対応

旧パスは整理前の `cilium-lab/` 直下を基準とする。分割文書の詳細は次節を参照する。

| 旧パス | 新しい参照先 |
|---|---|
| `bgp-config-change-proposal.md` | [design/bgp-config-change-proposal.md](../design/bgp-config-change-proposal.md) |
| `bgp-maintenance-and-route-drain.md` | [runbooks/bgp-maintenance-and-route-drain.md](../runbooks/bgp-maintenance-and-route-drain.md) |
| `bgp-route-aggregation-design.md` | [design/bgp-route-aggregation-design.md](../design/bgp-route-aggregation-design.md) |
| `checksum-compat-operations.md` | [runbooks/checksum-compat-operations.md](../runbooks/checksum-compat-operations.md) |
| `cilium-configuration-parameters.md` | [design/cilium-configuration-parameters.md](../design/cilium-configuration-parameters.md) |
| `cli-lab-flowfix-build.md` | [reference/cli-lab-flowfix-build.md](cli-lab-flowfix-build.md) |
| `client-tools.md` | [runbooks/client-tools.md](../runbooks/client-tools.md) |
| `clustermesh-fabric-dci-and-acceptance.md` | [design/clustermesh-fabric-dci-and-acceptance.md](../design/clustermesh-fabric-dci-and-acceptance.md) |
| `current-environment-change-plan.md` | [design/current-environment-change-plan.md](../design/current-environment-change-plan.md) |
| `egress-clustermesh-coexistence-test.md` | [tests/egress-clustermesh-coexistence-test.md](../tests/egress-clustermesh-coexistence-test.md) |
| `egress-gateway-routed-design.md` | [design/egress-gateway-routed-design.md](../design/egress-gateway-routed-design.md) |
| `egress-gateway-test-plan.md` | [tests/egress-gateway-test-plan.md](../tests/egress-gateway-test-plan.md) |
| `egress-interface-init-validation-2026-09-12.md` | [results/singlesite/2026-09-12/egress-interface-init-validation-2026-09-12.md](../results/singlesite/2026-09-12/egress-interface-init-validation-2026-09-12.md) |
| `execution-environment-singlesite-k02.md` | [runbooks/execution-environment-singlesite-k02.md](../runbooks/execution-environment-singlesite-k02.md) |
| `kernel-checksum-candidates.md` | [reference/kernel-checksum-candidates.md](kernel-checksum-candidates.md) |
| `kernel-compatibility-policy.md` | [runbooks/kernel-compatibility-policy.md](../runbooks/kernel-compatibility-policy.md) |
| `network-policy-and-tetragon-test-plan.md` | [tests/network-policy-and-tetragon-test-plan.md](../tests/network-policy-and-tetragon-test-plan.md) |
| `parameter-and-address-allocation.md` | [design/parameter-and-address-allocation.md](../design/parameter-and-address-allocation.md) |
| `references.md` | [reference/references.md](references.md) |
| `requirements-and-design.md` | [design/requirements-and-design.md](../design/requirements-and-design.md) |
| `resource-and-preflight.md` | [runbooks/resource-and-preflight.md](../runbooks/resource-and-preflight.md) |
| `singlesite-regression-validation-2026-09-12.md` | [results/singlesite/2026-09-12/singlesite-regression-validation-2026-09-12.md](../results/singlesite/2026-09-12/singlesite-regression-validation-2026-09-12.md) |
| `stage-artifact-inventory.md` | [reference/stage-artifact-inventory.md](stage-artifact-inventory.md) |
| `test-workloads.md` | [tests/test-workloads.md](../tests/test-workloads.md) |
| `validation-status-2026-08-30.md` | [results/singlesite/2026-08-30/validation-status-2026-08-30.md](../results/singlesite/2026-08-30/validation-status-2026-08-30.md) |
| `validation-status-2026-09-06.md` | [results/singlesite/2026-09-06/validation-status-2026-09-06.md](../results/singlesite/2026-09-06/validation-status-2026-09-06.md) |
| `validation-status-2026-09-12.md` | [results/singlesite/2026-09-12/validation-status-2026-09-12.md](../results/singlesite/2026-09-12/validation-status-2026-09-12.md) |
| `cli-lab-flowfix/` | [reference/cli-lab-flowfix/](cli-lab-flowfix/)（パッチ・checksum 等は内容を維持） |

## 分割と集約

| 元の文書 | 整理後の役割 |
|---|---|
| `README.md` | [入口](../README.md) に限定。[旧本文](../results/singlesite/2026-09-06/lab-overview-2026-09-06.md) は履歴へ保存 |
| `build-plan.md` 3.1 | 最新の進捗を [status](../status.md) へ集約。構築順序と受入チェックは元の文書に維持 |
| `execution-environment-singlesite-k02.md` | [現行の接続・準備・バイナリ配布](../runbooks/execution-environment-singlesite-k02.md) と [旧メモ全体の履歴](../results/singlesite/2026-09-12/execution-environment-history-2026-09-12.md) に分離 |
| `network-policy-and-tetragon-test-plan.md` | [共通 1〜3・6〜7](../tests/network-policy-and-tetragon-test-plan.md)、[Network Policy 4](../tests/network-policy-test-plan.md)、[Tetragon 5](../tests/tetragon-test-plan.md) |
| `egress-gateway-test-plan.md` | [共通 1〜5・7・11・12 の条件／撤去・13](../tests/egress-gateway-test-plan.md)、[基本機能 6・8・9・12.5〜12.6](../tests/egress-gateway-functional-tests.md)、[計画切替・異常系 10・12.1〜12.4・12.7](../tests/egress-gateway-failure-tests.md)、[性能 12.8〜12.9](../tests/egress-gateway-performance-tests.md) |

## レビューの入口

1. [README](../README.md) から目的の文書にたどれるかを確認する。
2. [status](../status.md) の現在値・未完了・保留の区別を確認する。
3. [試験手順一覧](../tests/README.md) と各共通手順で、準備・実施・撤去の順序を確認する。

`images/` と生の試験証跡は移動しない。実環境への接続・設定変更や試験実行は今回の文書整理に含めない。
