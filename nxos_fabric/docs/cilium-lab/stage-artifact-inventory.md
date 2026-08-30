# Stage 成果物台帳

## 1. 目的

この台帳は、[段階的な構築計画](build-plan.md)で必要となる設定、manifest、script、試験手順の
作成状態を管理する。`Created` は実ファイルの作成と offline render が完了したことを意味し、
稼働環境での apply／合格を意味しない。実行結果が合格した成果物だけを `Validated` とする。

## 2. Stage 別成果物

| Stage | 成果物 | 実ファイル／文書 | 状態 |
|---|---|---|---|
| Stage 0 | 要件・設計・address 台帳 | `requirements-and-design.md`、`cilium-configuration-parameters.md`、`parameter-and-address-allocation.md` | `Created` |
| Stage 0 | 現環境からの変更計画 | `current-environment-change-plan.md` | `Created` |
| Stage 0 | host／Kind preflight | `scripts/cilium-lab/preflight-host-and-kind.sh`、`resource-and-preflight.md` | `Created` |
| Stage 0 | CLI／chart version lock | site 別 `client/tool-versions.env`、`client/chart-versions.env` | `Created` |
| Stage 0 | CLI／chart 準備 | `scripts/k8s-client/prepare-tools.sh`、`scripts/cilium-lab/prepare-helm-charts.sh` | `Created` |
| Stage 0 | kind 初期設定 | single-site／multisite の `k02.kind.yaml`、multisite の `k03.kind.yaml` | `Created` |
| Stage 1 | Cilium 基盤 Helm values | site 別 `cilium/values/00-base.yaml` | `Created` |
| Stage 1 | Hubble 初期 Helm values | site 別 `cilium/values/10-observability.yaml` | `Created` |
| Stage 1 | API endpoint values 生成 | `scripts/cilium-lab/render-k8s-api-values.sh` | `Created` |
| Stage 1 | kubelet Fabric Node IP | `scripts/cilium-lab/configure-kubelet-node-ip.sh` | `Created` |
| Stage 1 | Cilium／Hubble の受入手順 | `build-plan.md` Stage 1、site 別 `cilium/README.md` | `Created` |
| Stage 2A | LB IPAM pool | site 別 `cilium/resources/10-lb-ipam.yaml` | `Created` |
| Stage 2A | normal BGP profile | site 別 `cilium/resources/20-bgp.yaml` | `Created` |
| Stage 2A | planned-shut BGP profile | site 別 `cilium/resources/21-bgp-planned-shut.yaml` | `Created` |
| Stage 2A | worker-only speaker label | `scripts/cilium-lab/configure-cilium-node-labels.sh` | `Created` |
| Stage 2A | aggregate blackhole | `scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh` | `Created` |
| Stage 2A | dual-stack LB smoke workload | single-site `cilium/manifests/validation/lab-smoke/` | `Created` |
| Stage 2A | single-site LB／BGP 実行手順 | single-site `cilium/manifests/validation/lab-smoke/README.md` | `Created` |
| Stage 2A | NX-OS 設計／確認手順 | `bgp-config-change-proposal.md`、`bgp-route-aggregation-design.md`、`bgp-maintenance-and-route-drain.md` | `Created` |
| Stage 2B | Egress feature values | single-site `cilium/values/20-singlesite-egress.yaml` | `Created` |
| Stage 2B | Egress secondary address | `scripts/cilium-lab/configure-egress-gateway-addresses.sh` | `Created` |
| Stage 2B | probe workload | single-site `cilium/manifests/validation/egress/base/` | `Created` |
| Stage 2B | `gw-a`／`gw-b` Policy | single-site `cilium/manifests/validation/egress/gw-a/`、`gw-b/` | `Created` |
| Stage 2B | 手動 failover／外部観測手順 | `test-workloads.md`、`build-plan.md` Stage 2B | `Created` |
| Stage 3 | Network Policy workload | single-site `cilium/manifests/validation/network-policy/base/` | `Created` |
| Stage 3 | default-deny／DNS／L3-L4／identity／FQDN／HTTP layer | single-site `cilium/manifests/validation/network-policy/10-*`～`60-*` | `Created` |
| Stage 3 | Hubble と Policy の判断手順 | `network-policy-and-tetragon-test-plan.md` | `Created` |
| Stage 4 | Tetragon observe-only values | site 別 `tetragon/values/00-observe-only.yaml` | `Created` |
| Stage 4 | process／file／network／capability TracingPolicy | single-site `cilium/manifests/validation/tetragon/10-*`～`40-*` | `Created` |
| Stage 4 | event／resource／failure safety 手順 | `network-policy-and-tetragon-test-plan.md` | `Created` |
| Stage 5 | Cluster Mesh Helm values | multisite k02／k03 `cilium/values/20-multisite-clustermesh.yaml` | `Created` |
| Stage 5 | API 固定 VIP Service | multisite k02／k03 `cilium/resources/30-clustermesh-apiserver-service.yaml` | `Created` |
| Stage 5 | 共通 CA 準備 | `scripts/cilium-lab/prepare-clustermesh-shared-ca.sh` | `Created` |
| Stage 5 | Global Service／local affinity demo | multisite k02／k03 `cilium/manifests/validation/clustermesh-demo/` | `Created` |
| Stage 5 | Fabric／DCI／partition 受入手順 | `clustermesh-fabric-dci-and-acceptance.md` | `Created` |
| Stage 6 | Egress／Cluster Mesh 同時有効化試験計画 | `egress-clustermesh-coexistence-test.md` | `Created` |
| Final | `singlesite-final` inventory | single-site `cilium/profiles/singlesite-final.list` | `Created` |
| Final | `multisite-final` inventory | multisite `k8s_kind/profiles/multisite-final.list` | `Created` |
| Final | offline render／収束 driver | `scripts/cilium-lab/render-cilium-lab.sh`、`converge-cilium-lab.sh` | `Created` |

## 3. Offline 検証済み範囲

次を cluster へ接続せずに実行済みである。

- Cilium chart `1.20.1` の single-site k02、multisite k02／k03 render
- Tetragon chart `1.7.0` の single-site k02、multisite k02／k03 render
- すべての Kustomize validation layer の render
- render 結果の `SHA256SUMS` 生成
- Cilium lab script の `bash -n`
- final profile の check-only 収束 driver

runtime directory と `/tmp` の render 証拠は Git 管理外とする。

## 4. 2026-08-30 実環境検証状況

single-site `adc-k02` では Stage 0／1 の初期構築、Stage 2A の基本通信、Stage 3 の `NP-00`～`NP-07` を
実施した。Stage 2A の Forwarding／ECMP 冗長性は `TI-001`／`TI-002`、Stage 4 は `TG-00`～`TG-08` が
未完了である。詳細は
[2026-08-30 検証スナップショット](validation-status-2026-08-30.md)を参照する。

| Stage | 実環境で確認した範囲 | 判定 |
|---|---|---|
| Stage 0 | host／Kind preflight、resource baseline | 条件付き合格 |
| Stage 1 | Cilium、Hubble、Tetragon の install／readiness | 合格 |
| Stage 2A | LB IPAM、BGP 8 session、dual-stack Service、RIB／EVPN | 基本機能合格、冗長性判定継続 |
| Stage 2B | Egress Gateway | 未実施 |
| Stage 3 | Network Policy `NP-00`～`NP-07` | 合格 |
| Stage 4 | Tetragon built-in process event | baseline 合格、本試験未実施 |
| Stage 5／6 | Cluster Mesh、Egress Gateway との同時有効化 | 未実施 |

## 5. 未作成ではなく、実環境情報が必要な成果物

次は manifest の設計不足ではなく、現行機器／稼働 cluster の情報または実測が必要なため、
汎用ファイルとして確定できない。

| 成果物 | 必要な入力 | 推奨する作成時期 |
|---|---|---|
| ADC single-site device 別 NX-OS candidate | 1／2 系の投入順と candidate は作成済み。NX-OS parser と running state の受入結果 | Stage 2A 適用時 |
| ADC multisite／BDC device 別 NX-OS candidate | running-config、BGP policy sequence、NX-OS parser、投入順 | Stage 5 の保守作業準備時 |
| DCI BGW device 別 route-map | 現行 export／import policy、route-target、sequence number | Stage 5 の保守作業準備時 |
| Cluster Mesh DNS change | DNS owner、zone、適用先 | Stage 5 前 |
| server-side dry-run／`kubectl diff` 記録 | 対象 CRD が存在する running cluster | 各 Stage の apply 直前 |
| multisite resource baseline／閾値確定 | k02／k03 同時起動 host の pre／post 実測 | multisite 展開時 |
| SNAT capacity profile | resource 実測、許容 connection 数、試験時間 | Stage 2B 基本合格後 |

これらが未完了の間は対応する Stage を `Validated` にしない。single-site resource baseline は
`resource-and-preflight.md` に記録済みであり、multisite の値は k02／k03 同時起動時に別途判定する。
