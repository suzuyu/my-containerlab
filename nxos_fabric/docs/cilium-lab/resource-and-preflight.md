# リソース設計と Kernel／Kind Node preflight

## 1. 適用範囲

最初に実行ホスト上で `adc-k02` だけを起動し、
Cilium、Envoy、Hubble Agent／Relay／UI、Tetragon Agent／Operator を導入した状態で実測する。
試験アプリは測定対象から除外し、基盤コンポーネントは初期構築手順に含める。

Tetragon は Cilium と同じ Helm release ではないため、Cilium の Ready 確認後に別 Helm release として
導入する。ただし、リソース判定上は両 release の導入完了を「初期構築完了」と扱う。

## 2. 初期リソース方針

初回測定では Cilium／Hubble／Tetragon の memory limit を設定しない。limit による OOMKill と実使用量を
混同せず、idle、疎通、観測イベント発生時の使用量を測るためである。実測後に p95 と最大値へ余裕を加え、
requests／limits を別変更で設定する。

| 判定項目 | 初期合格値 | 推奨運用値 | 判定理由 |
|---|---:|---:|---|
| 初期構築前 `MemAvailable` | `8192 MiB` 以上 | `12288 MiB` 以上 | 基盤追加と一時的な image pull／rollout の余裕を確保する |
| 初期構築後 `MemAvailable` | `4096 MiB` 以上 | `8192 MiB` 以上 | 障害調査、Agent 再起動、試験アプリ追加の余裕を残す |
| swap 使用量 | `0 MiB` | `0 MiB` | latency と BPF map／Agent の挙動を swap から分離する |
| Cilium／Hubble／Tetragon 増分 memory | `4096 MiB` 以下 | `3072 MiB` 以下 | 3 Node の初期 lab profile に対する暫定上限 |
| 基盤 component の OOMKill | `0` | `0` | 1 件でも不合格 |
| 基盤 component の restart | 安定化後 `0` | `0` | install／rollout 中の restart は原因を記録する |
| idle CPU 増分 | 5 分 p95 で `200%` 以下 | `100%` 以下 | host 全体ではなく対象 container の合計で判定する |

この値は本番 sizing ではなく、実行ホスト上で multisite へ進む可否を判定する lab gate である。
single-site 合格後も、k02／k03 の同時起動前に同じ preflight を再実行する。

## 3. ホスト OS 要件

| 項目 | 必須値 | 本ラボでの扱い |
|---|---|---|
| Architecture | `x86_64` または `aarch64` | `x86_64` を使用する |
| Linux kernel | `5.10.0` 以上 | Cilium `1.20.1` の最低要件として hard fail にする |
| cgroup | cgroup v2 | Socket LB と Kind Node の分離を確認する |
| cgroup namespace | host と各 Kind Node で別 namespace | 各 Node 間も重複しないことを確認する |
| BTF | `/sys/kernel/btf/vmlinux` が読める | Tetragon と eBPF の preflight で hard fail にする |
| bpffs | Cilium 導入後に `/sys/fs/bpf` へ mount | 導入前は warning、導入後は必須とする |
| Kernel config | BPF／BTF、crypto、cgroup BPF、TC、ingress、perf、scheduler、VXLAN／Geneve、FIB rules | `y` または `m` を確認する |
| Netfilter config | iptables masquerade 用 IP set／comment、L7 用 TPROXY／mark／CT／socket | single-site と multisite の両 profile を実行できるよう superset を確認する |
| Reverse path filter | `all=0`、`default=0` | 複数 NIC／非対称経路の誤 drop を避ける |
| Swap | 未使用 | swap 領域の存在は許容し、使用中なら warning とする |
| Node Fabric MTU | `9100` | Cilium／Pod MTU `9000` を収容する |
| Kind Node image | digest 固定の `v1.35.5` | tag だけでなく digest を比較する |

必要な Fabric／DCI port は [Cluster Mesh Fabric／DCI 境界設計](clustermesh-fabric-dci-and-acceptance.md)で
管理する。

## 4. Preflight スクリプト

共通スクリプトは `nxos_fabric/scripts/cilium-lab/preflight-host-and-kind.sh` である。

ホストだけを確認する。

```bash
nxos_fabric/scripts/cilium-lab/preflight-host-and-kind.sh \
  --host-only \
  --min-available-mib 8192
```

Kind Node、Fabric interface、route、Node label まで確認する。

```bash
nxos_fabric/scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster adc-k02 \
  --kube-context kind-adc-k02 \
  --min-available-mib 8192
```

`bdc-k03` では `--cluster bdc-k03` と該当 context を指定する。終了 code `0` を合格とし、`FAIL` が
1 件でもあれば Cilium install へ進まない。`WARN` は理由と採否を実施記録へ残す。

## 5. 2026-08-29 の実行結果

現在のホストでは次を確認した。

| 項目 | 実測 | 判定 |
|---|---:|---|
| Kernel | `5.14.0-611.49.1.el9_7.x86_64` | Pass |
| CPU | `18` logical CPU | 記録 |
| Total memory | 約 `122.3 GiB` | 記録 |
| `MemAvailable` | `3104-3115 MiB` | Fail |
| Swap 使用 | `0 MiB` | Pass |
| cgroup v2／BTF／kernel config | 要件を満たす | Pass |
| `rp_filter` | `all=0`、`default=0` | Pass |
| 稼働中 k02 image | `kindest/node:v1.34.3` | 計画値 `v1.35.5` に対して Fail |
| k02 Fabric MTU／route | `9100`、期待する `/16`／`/48` route | Pass |
| bpffs | Cilium 未導入のため未 mount | Warning |

`adc-k02` を対象とした再実行結果は `PASS=68 WARN=6 FAIL=4` である。4 件の Fail は
`MemAvailable` 1 件と、稼働中の 3 Node が計画値とは異なる `v1.34.3` であることの 3 件に限定された。
IPv4／IPv6 address、Fabric interface、MTU、route、cgroup、BTF は合格している。6 件の Warning は
Cilium 導入前の bpffs 未 mount 3 件と、`--kube-context` を付けず Node label を未確認とした 3 件である。

この Fail はホスト能力不足の確定ではない。multisite の NX-OS／Kind container が同時起動中の測定であるため、
single-site だけの構成へ切り替えた後に再判定する。再測定で `MemAvailable < 8192 MiB` の場合は、
不要な lab container の停止または対象 component の分離を先に検討する。

## 6. 2026-08-30 single-site k02 初期構築結果

別の single-site 実行ホストで `adc-k02` だけを対象に、Cilium `1.20.1`、Hubble、Tetragon `1.7.0`、
LB IPAM／BGP resource を初期構築した。実行ホストの管理 IP は実測記録に含めない。

| 項目 | 実測 | 判定 |
|---|---:|---|
| 初期構築前 `MemAvailable` | `48033 MiB` | Pass |
| 10 分 idle 後 `MemAvailable` | `43687 MiB` | Pass。推奨運用値を満たす |
| host 全体の `MemAvailable` 差分 | `4346 MiB` | 暫定上限を `250 MiB` 超過。component 単独値ではないため継続観測 |
| Kind Node container memory 合計 | 約 `4.99 GiB` | Kubernetes 基盤を含む参考値 |
| idle CPU p95 | `102.85%`、60 sample | 初期合格値を満たし、推奨運用値を `2.85%` 超過 |
| idle CPU 最大値 | `117.10%` | 初期合格値内 |
| swap 使用量 | 導入前約 `127 MiB`、導入後 `128 MiB` | Warning。増分は軽微だが `0 MiB` 基準は未達 |
| Pod restart | `0` | Pass |
| kernel OOMKill | `0` | Pass |
| Hubble certificate 生成 Pod | `Succeeded`、restart `0` | Pass |
| Cilium／Hubble／Tetragon | 全対象 Ready | Pass |
| post-install preflight | `FAIL=0`、全 Node の bpffs mount 済み | Pass |

single-site の resource gate は条件付き合格とし、Stage 2A の validation workload 適用へ進める。CPU p95 の
推奨値超過、host 全体の memory 差分、swap 使用は例外／継続観測項目として残す。初期 platform の最終受入は
`lab-smoke` で Hubble flow と Tetragon process event を取得してから確定する。multisite の sizing 合格を
意味しないため、k02／k03 同時起動前と起動後に同じ形式で再測定する。

`PASS`／`WARN` の固定件数は合格条件にしない。preflight は `FAIL=0` を必須とし、初期構築後の bpffs 未 mount、
BGP speaker label 未確認など、解消すべき `WARN` が残る場合は合格としない。swap の `WARN` は使用量と
導入前後の変化を別途評価する。

## 7. 使用量の記録と合否判断

初期構築直前、Cilium 完了後、Tetragon 完了後、10 分 idle 後の 4 点で同じ形式を記録する。

```bash
date -Is
free -h
docker stats --no-stream \
  adc-k02-control-plane \
  adc-k02-worker \
  adc-k02-worker2
kubectl --context kind-adc-k02 -n kube-system top pods 2>/dev/null || true
kubectl --context kind-adc-k02 get pods -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
journalctl -k --since '-15 min' --no-pager | grep -Ei 'oom|out of memory|killed process' || true
```

idle CPU は対象 Kind Node container の合計を 60 回取得し、nearest-rank 法で p95 を算出する。

```bash
for sample in $(seq 1 60); do
  docker stats --no-stream --format '{{.CPUPerc}}' \
    adc-k02-control-plane \
    adc-k02-worker \
    adc-k02-worker2 | \
    tr -d '%' | \
    awk -v timestamp="$(date -Is)" \
      '{total += $1} END {print timestamp, total}'
  sleep 5
done | tee /tmp/k02-idle-cpu.txt

LC_ALL=C sort -n -k2,2 /tmp/k02-idle-cpu.txt | \
  awk '{
    value[NR]=$2
  }
  END {
    p95_pos=int((NR * 95 + 99) / 100)
    printf "samples=%d CPU_p95_percent=%.2f\n", NR, value[p95_pos]
  }'
```

metrics-server を初期 component に追加しないため、`kubectl top` が利用できない場合は
`docker stats`、cgroup memory、component metrics を正本とする。試験アプリを追加する前に、次がすべて成立すれば
single-site のリソース設計を暫定合格とする。

1. preflight の `FAIL=0`。
2. `cilium status --wait` と Tetragon DaemonSet／Operator rollout が成功する。
3. 初期構築後の `MemAvailable` が `4096 MiB` 以上で、OOMKill がない。swap 使用中の場合は、導入前後の
   使用量と増減を記録して例外採否を判断する。
4. 10 分 idle 後に restart が増加せず、増分 memory／CPU が表の閾値内に収まる。
5. Hubble flow と Tetragon process event を 1 件以上取得できる。

## 8. 参照 URL

- [Cilium System Requirements](https://docs.cilium.io/en/stable/operations/system_requirements/)
- [Cilium Installation Using Kind](https://docs.cilium.io/en/stable/installation/kind/)
- [Tetragon Kubernetes Installation](https://tetragon.io/docs/installation/kubernetes/)
