# bdc-k03 Cilium 初期構築ファイル

このディレクトリは、`bdc-k03` を Cilium `v1.20.1` で初期構築するための Helm values を管理する。
コマンドは `nxos_fabric/nxos_multisite` を作業ディレクトリとして実行する。

## ファイル

| Path | 管理 | 用途 |
|---|---|---|
| `values/00-base.yaml` | Git | CNI、datapath、LB IPAM／BGP feature gate の固定設計値 |
| `values/10-observability.yaml` | Git | Hubble Agent／Relay、TLS、dynamic metrics |
| `values/20-multisite-clustermesh.yaml` | Git | Cluster Mesh API、VIP、DNS、TLS |
| `resources/10-lb-ipam.yaml` | Git | `infra`／`app` の dual-stack pool |
| `resources/20-bgp.yaml` | Git | worker 2 Node の BGP peer／advertisement／source address |
| `resources/21-bgp-planned-shut.yaml` | Git | Node label で切り替える graceful-shutdown community 付き BGP profile |
| `resources/30-clustermesh-apiserver-service.yaml` | Git | 固定 VIP の dual-stack Cluster Mesh API Service |
| `../tetragon/values/00-observe-only.yaml` | Git | Tetragon observe-only 初期 values |
| `runtime/10-k8s-api.yaml` | Git 管理外 | control-plane `eth0` から生成する API endpoint |
| `runtime/20-coredns-upstream.env` | Git 管理外 | 実行環境で選定した Pod 到達可能な CoreDNS upstream |

固定 values では、dual-stack Kubernetes IPAM、VXLAN、kube-proxy replacement、MTU `9000`、
multi-device、Fabric 側 NodePort address、BGP Control Plane、Hubble、Cluster Mesh API を初回から
有効化する。Cluster Mesh API は worker 2 Node に 1 Pod ずつ配置する 2 replica、PDB
`minAvailable: 1`、外部 Service `ClientIP` affinity で構築する。Hubble UI は k02 だけに配置し、k03 では
無効とする。Egress Gateway、MCS API、試験アプリは初期構築に含めない。

Cluster Mesh の構成根拠は [Cilium Cluster Mesh Setup](https://docs.cilium.io/en/stable/network/clustermesh/setup/) と
[Cilium Helm Reference](https://docs.cilium.io/en/stable/helm-values/) を参照する。

worker 2 Node だけに BGP speaker label を付与し、preflight を通過してから install する。

```bash
../scripts/cilium-lab/configure-cilium-node-labels.sh --context kind-bdc-k03 --apply
../scripts/cilium-lab/preflight-host-and-kind.sh \
  --cluster bdc-k03 \
  --kube-context kind-bdc-k03
```

## API endpoint values の生成

Kind Node と Fabric interface の作成後、Cilium を導入する前に実行する。

```bash
../scripts/cilium-lab/render-k8s-api-values.sh \
  --cluster bdc-k03 \
  --output k8s_kind/k03/cilium/runtime/10-k8s-api.yaml
```

スクリプトは control-plane `eth0` の IPv4 address を取得し、全 k03 Node から API `/livez` を確認してから
`k8sServiceHost` と `k8sServicePort` を出力する。生成ファイルは commit しない。

## 静的 render

```bash
helm template cilium oci://quay.io/cilium/charts/cilium \
  --version 1.20.1 \
  --namespace kube-system \
  --kube-context kind-bdc-k03 \
  --values k8s_kind/k03/cilium/values/00-base.yaml \
  --values k8s_kind/k03/cilium/values/10-observability.yaml \
  --values k8s_kind/k03/cilium/values/20-multisite-clustermesh.yaml \
  --values k8s_kind/k03/cilium/runtime/10-k8s-api.yaml \
  > /tmp/cilium-k03-rendered.yaml
```

## 導入

実行前に render 差分と現在の Helm release を確認する。k03 へ Cilium を install する前に、公式手順に従って
k02 の共通 CA をコピーする。スクリプトは最初に fingerprint を比較し、異なる場合は check-only で停止する。

```bash
../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
  --source-context kind-adc-k02 \
  --target-context kind-bdc-k03

# target Secret が存在しないことを確認した初期構築でだけ追加する。
../scripts/cilium-lab/prepare-clustermesh-shared-ca.sh \
  --source-context kind-adc-k02 \
  --target-context kind-bdc-k03 \
  --apply
```

既存 CA が異なる場合、`--apply` は置換せずに停止する。`--replace-existing` は k03 の Cilium 証明書を含む
専用保守手順を作成した場合だけ使用し、通常の再実行では使用しない。

ユーザーがクラスタへの適用を明示した後に実行する。

```bash
helm upgrade --install cilium oci://quay.io/cilium/charts/cilium \
  --version 1.20.1 \
  --namespace kube-system \
  --kube-context kind-bdc-k03 \
  --values k8s_kind/k03/cilium/values/00-base.yaml \
  --values k8s_kind/k03/cilium/values/10-observability.yaml \
  --values k8s_kind/k03/cilium/values/20-multisite-clustermesh.yaml \
  --values k8s_kind/k03/cilium/runtime/10-k8s-api.yaml \
  --wait \
  --timeout 10m
```

## CoreDNS upstream の設定

CoreDNS upstream は環境依存のため、固定 manifest へ保存しない。`--upstream`、環境変数
`COREDNS_UPSTREAM_DNS`、host `/etc/resolv.conf` の非 loopback IPv4 nameserver の順で値を選択する。

```bash
../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-bdc-k03 \
  --record k8s_kind/k03/cilium/runtime/20-coredns-upstream.env

../scripts/cilium-lab/configure-coredns-upstream.sh \
  --context kind-bdc-k03 \
  --record k8s_kind/k03/cilium/runtime/20-coredns-upstream.env \
  --apply
```

自動検出値を使用できない環境では、`--upstream` または `COREDNS_UPSTREAM_DNS` で Pod から到達可能な
IPv4 resolver を指定する。スクリプトは変更前後の DNS test と失敗時 rollback を行い、選定値を Git 管理外の
runtime record に保存する。

Cilium が Ready になった後、pool／BGP resource と Tetragon を導入する。

```bash
cilium status --context kind-bdc-k03 --wait
../scripts/cilium-lab/configure-bgp-aggregate-blackhole.sh \
  --cluster bdc-k03 --action apply
kubectl --context kind-bdc-k03 apply \
  -f k8s_kind/k03/cilium/resources/10-lb-ipam.yaml \
  -f k8s_kind/k03/cilium/resources/20-bgp.yaml \
  -f k8s_kind/k03/cilium/resources/21-bgp-planned-shut.yaml \
  -f k8s_kind/k03/cilium/resources/30-clustermesh-apiserver-service.yaml

helm upgrade --install tetragon cilium/tetragon \
  --version 1.7.0 \
  --namespace kube-system \
  --kube-context kind-bdc-k03 \
  --values k8s_kind/k03/tetragon/values/00-observe-only.yaml \
  --wait \
  --timeout 10m
```

`bdc-k03` には MetalLB を導入しない。
