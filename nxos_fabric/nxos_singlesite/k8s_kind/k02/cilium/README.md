# adc-k02 Cilium 初期構築手順

このディレクトリは、`adc-k02` を Cilium `v1.20.1` で初期構築するための Helm values を管理する。
コマンドは `nxos_fabric/nxos_singlesite` を作業ディレクトリとして実行する。

## ファイル

| Path | 管理 | 用途 |
|---|---|---|
| `values/00-base.yaml` | Git | CNI、datapath、LB IPAM／BGP feature gate の固定設計値 |
| `values/10-observability.yaml` | Git | Hubble Agent／Relay／UI、TLS、dynamic metrics |
| `values/20-singlesite-egress.yaml` | Git | BPF masquerade と Egress Gateway feature gate |
| `resources/10-lb-ipam.yaml` | Git | `infra`／`app` の dual-stack pool |
| `resources/20-bgp.yaml` | Git | worker 2 Node の BGP peer／advertisement／source address |
| `resources/21-bgp-planned-shut.yaml` | Git | Node label で切り替える graceful-shutdown community 付き BGP profile |
| `manifests/validation/` | Git | 初期構築と分離した smoke、Egress、Network Policy、Tetragon 試験 layer |
| `../tetragon/values/00-observe-only.yaml` | Git | Tetragon observe-only 初期 values |
| `../../client/chart-versions.env` | Git | Cilium／Tetragon Helm chart の固定 version |
| `../../client/runtime/charts/` | Git 管理外 | 検証済み Helm chart cache |
| `runtime/10-k8s-api.yaml` | Git 管理外 | control-plane `eth0` から生成する API endpoint |
| `runtime/20-coredns-upstream.env` | Git 管理外 | 実行環境で選定した Pod 到達可能な CoreDNS upstream |

固定 values では、dual-stack Kubernetes IPAM、VXLAN、kube-proxy replacement、MTU `9000`、
multi-device、Fabric 側 NodePort address、BGP Control Plane、Hubble、Egress Gateway を初回から
有効化する。Egress policy と試験アプリだけは初期構築に含めない。

## CLI バイナリ準備と PATH 設定

`helm template` を実行する前に、version を固定した Helm、kubectl、Cilium CLI、Hubble CLI を
Git 管理外の runtime directory へ準備する。system-wide にはインストールせず、この作業 shell の
`PATH` の先頭へ追加する。

```bash
../scripts/k8s-client/prepare-tools.sh \
  --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh \
  --profile k8s_kind/client \
  --check

K8S_CLIENT_RUNTIME="$PWD/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r

command -v helm kubectl cilium hubble
helm version --short
kubectl version --client
cilium version --client
hubble version
```

この手順では `KUBECONFIG` を変更しない。次節で Containerlab が生成した k02 用 kubeconfig を指定する。
新しい shell で作業を再開した場合は、バイナリの再取得は不要だが、`PATH` の設定を再実行する。

## Helm chart cache の準備

固定 version の Cilium／Tetragon chart を公式配布元から Git 管理外の runtime directory へ取得し、
chart 名と version を検証する。以降の静的 render と導入では、この local chart を共通して使用する。

```bash
../scripts/cilium-lab/prepare-helm-charts.sh \
  --profile k8s_kind/client
../scripts/cilium-lab/prepare-helm-charts.sh \
  --profile k8s_kind/client \
  --check

helm show chart k8s_kind/client/runtime/charts/cilium-1.20.1.tgz
helm show chart k8s_kind/client/runtime/charts/tetragon-1.7.0.tgz
```

## kubeconfig の準備

Containerlab が生成する k02 の kubeconfig は、lab 出力 directory 配下に保存される。次のコマンドは
`nxos_fabric/nxos_singlesite` を作業 directory として実行する。

```bash
export CLABNAME="nxos-fabric-singlesite"
export KUBECONFIG="$PWD/clab-${CLABNAME}/adc-k02/k8s_kind/k02/kubeconfig-k02"

ls -l "$KUBECONFIG"
test -r "$KUBECONFIG" || sudo chmod g+r "$KUBECONFIG"
kubectl config get-contexts
kubectl --context kind-adc-k02 get nodes
```

kubeconfig は client certificate と private key を含むため Git へ保存せず、world-readable にしない。
全 Node は Cilium 導入まで `NotReady` でよい。ここでは 3 Node が API から取得できることを確認する。

## Preflight と Node label

初期構築前に host、Kind Node、Fabric link を確認し、worker だけへ BGP speaker label を付与する。

```bash
../scripts/cilium-lab/preflight-host-and-kind.sh --host-only
../scripts/cilium-lab/configure-cilium-node-labels.sh \
  --context kind-adc-k02 --apply
../scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster adc-k02 \
  --kube-context kind-adc-k02
```

preflight 合格後、Cilium を導入する直前の resource baseline を記録する。

```bash
date -Is
awk '/^MemAvailable:/ {print "MemAvailable_MiB=" int($2 / 1024)}' /proc/meminfo
docker stats --no-stream \
  adc-k02-control-plane \
  adc-k02-worker \
  adc-k02-worker2
kubectl --context kind-adc-k02 get pods -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
```

## API endpoint values の生成

Kind Node と Fabric interface の作成後、Cilium を導入する前に実行する。

```bash
../scripts/cilium-lab/render-k8s-api-values.sh \
  --cluster adc-k02 \
  --output k8s_kind/k02/cilium/runtime/10-k8s-api.yaml
```

スクリプトは control-plane `eth0` の IPv4 address を取得し、全 k02 Node から API `/livez` を確認してから
`k8sServiceHost` と `k8sServicePort` を出力する。生成ファイルは commit しない。

## 静的 render

```bash
helm template cilium \
  k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/cilium/values/00-base.yaml \
  --values k8s_kind/k02/cilium/values/10-observability.yaml \
  --values k8s_kind/k02/cilium/values/20-singlesite-egress.yaml \
  --values k8s_kind/k02/cilium/runtime/10-k8s-api.yaml \
  > /tmp/cilium-k02-rendered.yaml

test -s /tmp/cilium-k02-rendered.yaml
```

## Cilium の導入

実行前に render 差分と現在の Helm release を確認し、ユーザーがクラスタへの適用を明示した後に実行する。

```bash
helm upgrade --install cilium \
  k8s_kind/client/runtime/charts/cilium-1.20.1.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/cilium/values/00-base.yaml \
  --values k8s_kind/k02/cilium/values/10-observability.yaml \
  --values k8s_kind/k02/cilium/values/20-singlesite-egress.yaml \
  --values k8s_kind/k02/cilium/runtime/10-k8s-api.yaml \
  --wait \
  --timeout 10m

helm status cilium \
  --namespace kube-system \
  --kube-context kind-adc-k02
cilium status --context kind-adc-k02 --wait
```

Single-site の初期構築では、`cilium status` の `ClusterMesh: disabled` は想定どおりである。
ClusterMesh は k02 と k03 を使用する multi-site 構築で有効化する。

## CoreDNS upstream の設定

Kind Node の `/etc/resolv.conf` は Docker 組み込み DNS を指す場合がある。CoreDNS Pod からその DNS へ到達できない
環境でも再利用できるよう、resolver IP は固定 manifest に保存せず、実行時パラメータとして設定する。

値の優先順位は `--upstream`、環境変数 `COREDNS_UPSTREAM_DNS`、Containerlab host の
`/etc/resolv.conf` から検出した最初の非 loopback IPv4 nameserver の順である。check-only で選定結果を確認してから
`--apply` を指定する。

```bash
../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env

../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env \
  --apply
```

host の nameserver が loopback、link-local、または Pod から到達できない場合は、環境固有値を明示する。

```bash
export COREDNS_UPSTREAM_DNS="${SITE_DNS_RESOLVER_IPV4:?set a Pod-reachable DNS resolver IPv4}"

../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-adc-k02 \
  --record k8s_kind/k02/cilium/runtime/20-coredns-upstream.env \
  --apply
```

スクリプトは direct upstream test、CoreDNS ConfigMap patch／rollout、Cluster DNS test を順に実施する。
適用後の test が失敗した場合は元の Corefile へ rollback する。選定値の runtime record は Git へ追加しない。

## LB IPAM／BGP resource の導入

Cilium が Ready になった後、worker 2 Node に集約 prefix の blackhole route を設定してから、
LB IPAM と BGP Control Plane resource を適用する。この段階では試験アプリを適用しない。

```bash
../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh \
  --cluster adc-k02 --action apply
kubectl --context kind-adc-k02 apply \
  -f k8s_kind/k02/cilium/resources/10-lb-ipam.yaml \
  -f k8s_kind/k02/cilium/resources/20-bgp.yaml \
  -f k8s_kind/k02/cilium/resources/21-bgp-planned-shut.yaml

kubectl --context kind-adc-k02 get \
  ciliumloadbalancerippools,ciliumbgpclusterconfigs
cilium bgp peers --context kind-adc-k02
```

worker 2 Node から ADC BGR 2 台へ IPv4／IPv6 で接続するため、合計 8 session が `Established` になることを
確認する。対象の LoadBalancer Service は後続試験で作成するため、この時点では広告経路がなくてもよい。

## Tetragon の導入

repository alias に依存せず、準備済みの local chart から observe-only profile を導入する。

```bash
helm upgrade --install tetragon \
  k8s_kind/client/runtime/charts/tetragon-1.7.0.tgz \
  --namespace kube-system \
  --kube-context kind-adc-k02 \
  --values k8s_kind/k02/tetragon/values/00-observe-only.yaml \
  --wait \
  --timeout 10m

helm status tetragon \
  --namespace kube-system \
  --kube-context kind-adc-k02
kubectl --context kind-adc-k02 -n kube-system rollout status daemonset/tetragon
kubectl --context kind-adc-k02 -n kube-system rollout status deployment/tetragon-operator
```

## 初期構築後の受入確認

Cilium、Hubble、Tetragon の状態と、Cilium 導入後の bpffs、Node label、Fabric interface を確認する。

```bash
cilium status --context kind-adc-k02 --wait
kubectl --context kind-adc-k02 get nodes
kubectl --context kind-adc-k02 -n kube-system get pods -o wide

../scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster adc-k02 \
  --kube-context kind-adc-k02
```

preflight は `FAIL=0` を必須とする。`PASS` と `WARN` の件数は、host、Node 数、検査項目によって
変動するため、固定の合格値としない。

`WARN` がある場合は内容を個別に確認する。swap 使用に関する `WARN` は、使用量、導入前からの増減、
性能および Cilium／Tetragon への影響をリソース判定で別途評価する。Cilium 導入後の bpffs 未 mount、
BGP speaker label 未確認など、初期構築完了時に解消すべき `WARN` が残っている場合は合格としない。

10 分 idle 後に resource、Pod restart、OOMKill の有無を記録する。

```bash
date -Is
free -h
awk '/^MemAvailable:/ {print "MemAvailable_MiB=" int($2 / 1024)}' /proc/meminfo
docker stats --no-stream \
  adc-k02-control-plane \
  adc-k02-worker \
  adc-k02-worker2
kubectl --context kind-adc-k02 get pods -A \
  -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
journalctl -k --since '-15 min' --no-pager | \
  grep -Ei 'oom|out of memory|killed process' || true
```

Hubble certificate 生成 Pod は常駐 Pod ではない。該当 Pod が存在する場合は `Succeeded`、restart `0` を確認する。

```bash
kubectl --context kind-adc-k02 -n kube-system get pods \
  -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount' | \
  awk 'NR == 1 || $1 ~ /^hubble-generate-certs-/'
```

対象 Kind Node container の CPU 合計を 60 回取得し、nearest-rank 法で p95 を計算する。

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

初期構築後の `MemAvailable` は `4096 MiB` 以上、OOMKill は 0 件、idle 後の restart 増加は 0 件を
最低合格値とする。Cilium／Hubble／Tetragon の増分 memory は `4096 MiB` 以下を暫定上限とし、
導入直前と 10 分 idle 後の同形式の記録を比較する。CPU p95 は `200%` 以下を初期合格値、`100%` 以下を
推奨運用値とする。詳細は
[リソース設計と preflight](../../../../docs/cilium-lab/resource-and-preflight.md)を参照する。

LoadBalancer VIP の割り当て、`/26`／`/112` の広告、Hubble flow、Tetragon event は、初期 platform の
resource 判定後に [Stage 2A lab-smoke 実行手順](manifests/validation/lab-smoke/README.md)から開始し、
`manifests/validation/` の試験 workload と policy を段階適用して確認する。

`lab-smoke` の初期合格後は、
[Network Policy／Tetragon 検証計画](../../../../docs/cilium-lab/network-policy-and-tetragon-test-plan.md)の
`NP-00` から後続試験を開始する。

既存の `manifest/` は旧 MetalLB／demo 検証用であり、Cilium 初期構築時に一括適用しない。
