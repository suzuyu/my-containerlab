# 2026-08-30 Single-site `adc-k02` 検証スナップショット

## 1. 目的と範囲

この文書は、2026-08-30 の作業終了時点における `nxos_singlesite` の `adc-k02` 検証状態を固定して残す。
設計上の初期値は各設計書、再実行手順は各 runbook を正本とし、この文書では実環境へ適用した範囲、判定、
未解決課題、次回の再開点をまとめる。

| 項目 | 実測環境 |
|---|---|
| Cluster | `adc-k02` |
| Kubernetes | `v1.35.5` |
| Cilium | `v1.20.1` |
| Tetragon | `v1.7.0` |
| Datapath | VXLAN、kube-proxy replacement、dual-stack |
| BGP | Cilium BGP Control Plane v2、worker 2 Node、ADC BGR 2 台 |

## 2. 進捗サマリー

| 範囲 | 2026-08-30 時点の結果 | 補足 |
|---|---|---|
| Stage 0 host／Kind preflight | 条件付き合格 | `FAIL=0`。swap、CPU p95、host 全体の memory 差分は継続観測 |
| Stage 1 Cilium／Hubble／Tetragon 初期構築 | 合格 | Cilium、Operator、Envoy、Hubble、Tetragon が Ready。Pod restart と kernel OOM は `0` |
| Stage 2A LB IPAM／BGP | 基本機能合格、冗長性判定継続 | VIP 割り当て、BGP session、RIB／EVPN、dual-stack 基本通信を確認。`TI-001`／`TI-002` を継続 |
| Stage 2B Egress Gateway | 未実施 | values、secondary address script、workload、Policy は作成済み |
| Stage 3 Network Policy | 合格 | `NP-00`～`NP-07` がすべて合格し、Policy rollback 後の baseline 復旧を確認 |
| Stage 4 Tetragon | baseline 合格、本試験未実施 | built-in `process_exec`／`process_exit` を確認。`TG-00`～`TG-08` は次回実施 |
| Stage 5 Cluster Mesh | 未実施 | multisite k02／k03 の values、resource、受入手順は作成済み |

## 3. 確認済みの状態

### 3.1 初期構築とリソース

- post-install preflight は `FAIL=0` で、全 Node の bpffs mount を確認した。
- 10 分 idle 後の `MemAvailable` は `43687 MiB`、Kind Node container memory 合計は約 `4.99 GiB` であった。
- idle CPU p95 は `102.85%`、最大値は `117.10%` であった。
- swap は導入前約 `127 MiB`、導入後 `128 MiB` であり、増分は軽微だが `0 MiB` 基準は未達である。
- Cilium、Hubble、Tetragon の対象 Pod は Ready で、意図しない restart と host kernel の OOM 記録はなかった。

詳細な測定値と合否条件は
[リソース設計と preflight](resource-and-preflight.md#6-2026-08-30-single-site-k02-初期構築結果)を参照する。
この結果は single-site の条件付き合格であり、k02／k03 を同時起動する multisite の容量合格を意味しない。

### 3.2 Cilium Service と BGP

- worker 2 Node から ADC BGR 2 台への IPv4／IPv6 BGP session、合計 8 session が `established` となった。
- Cilium LB IPAM から dual-stack VIP が割り当てられ、Cilium の advertised route、ADC BGR の RIB、
  Leaf の EVPN Type-5 route を確認した。
- `externalTrafficPolicy: Local` の NodePort と LoadBalancer は IPv4／IPv6 とも連続試験に合格した。
- `externalTrafficPolicy: Cluster` の IPv6 外部通信には `TI-001`、Nexus 9000v の Forwarding／ECMP 表示には
  `TI-002` が残るため、Service 冗長性全体は未合格とする。

### 3.3 Hubble と Tetragon

- Hubble Relay は 3／3 Node に接続し、Service 通信、DNS、TCP、HTTP、Policy の `FORWARDED`／`DROPPED` を
  CLI と UI で確認した。
- Hubble UI では `cilium-lab-policy` の service map と、`kube-system` の Hubble UI から Relay への flow を確認した。
- Tetragon は observe-only で稼働し、test Pod の `process_exec`／`process_exit` と Pod metadata を取得した。
- file、network、capability、負荷、DaemonSet 停止安全性を含む `TG-00`～`TG-08` は未実施である。

### 3.4 Network Policy

`NP-00`～`NP-07` はすべて合格した。

| Test ID | 結果 | 確認内容 |
|---|---|---|
| `NP-00` | 合格 | Policy なしで `tiefighter`／`xwing` が HTTP `200` |
| `NP-01` | 合格 | default-deny で DNS と application traffic を拒否 |
| `NP-02` | 合格 | CoreDNS 通信だけ復旧し、application traffic は拒否を維持 |
| `NP-03` | 合格 | `tiefighter` の L3／L4 通信だけ許可し、`xwing` を拒否 |
| `NP-04` | 合格 | Service Account identity 一致だけ許可 |
| `NP-05` | 合格 | FQDN の DNS 観測、許可先通信、非許可先拒否、FQDN cache を確認 |
| `NP-06` | 合格 | HTTP `POST` を許可し、`PUT` を L7 で拒否、非対象 source を拒否 |
| `NP-07` | 合格 | 全 Policy を削除し、baseline traffic、Hubble、Cilium／BGP health が復旧 |

試験終了時は NetworkPolicy／CiliumNetworkPolicy を削除済みであり、検証 workload は後続試験用に残した。

## 4. 課題と runtime 差分

| ID／項目 | 状態 | 2026-08-30 終了時点の扱い |
|---|---|---|
| `TI-001` | `Workaround prepared` | IPv6 Cluster Service の remote backend path は再現用に残し、試験継続時は Local Service を使用する |
| `TI-002` | `Open` | BGP／RIB／EVPN は確認済み。controlled withdraw と Forwarding／ECMP の最終判定を次回実施する |
| `TI-003` | `Workaround validated` | Pod から到達できる resolver を CoreDNS `forward` へ runtime 設定し、`NP-05` が合格した |
| Hubble CLI version | Warning | CLI `v1.19.4` と Relay `v1.20.1` の warning を記録した。healthcheck、3 Node 接続、flow 取得は成功した |

CoreDNS upstream の値は環境固有であるため Git 管理対象の manifest へ固定せず、
`configure-coredns-upstream.sh` が Git 管理外の runtime record へ保存する。

## 5. Evidence

生ログは次の Git 管理外ディレクトリに保存した。

```text
nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-08-30/adc-k02/
```

- raw log: 37 件
- integrity: `SHA256SUMS` の全 37 件が一致
- index: 同ディレクトリの `README.md`
- Git: `.gitignore` の `**/operations/*` により除外

公開可能な画面例は次の tracked file に保存した。

- [Hubble UI `cilium-lab-policy` の `NP-00`](images/hubble-ui-cilium-lab-policy-np00.png)
- [Hubble UI `kube-system` の Relay 通信](images/hubble-ui-kube-system-relay.png)

raw log には private management IP と password prompt が含まれるため Git へ追加しない。password 値、Secret、
token、private key、kubeconfig data の実値は検出されていない。

## 6. 次回の再開点

1. `TG-00`～`TG-08` の Tetragon 本試験を実施する。
2. `TI-001` の original packet capture と `cilium sysdump` を取得し、kernel／Cilium の恒久対処を再評価する。
3. `TI-002` の controlled withdraw を実施し、BGR／Leaf の RIB、FIB、ECMP、通信断時間を同時記録する。
4. Stage 2B の Egress Gateway を `gw-a` profile から実施する。
5. single-site の未解決事項を整理してから multisite k02／k03 の resource baseline と Cluster Mesh へ進む。

次回は、[試験課題台帳](test-issue-register.md)、
[Network Policy／Tetragon 検証計画](network-policy-and-tetragon-test-plan.md)、
[single-site k02 初期構築手順](../../nxos_singlesite/k8s_kind/k02/cilium/README.md)を入口とする。
