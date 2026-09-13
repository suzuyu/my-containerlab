# Multi-site Kubernetes client profile

このprofileはmulti-site labのk02/k03に接続し、Helm release を管理する CLI version と、Git 管理外 runtime の配置先を
定義する。共通準備スクリプトはリポジトリの
`nxos_fabric/scripts/k8s-client/prepare-tools.sh`を使用する。

```bash
cd nxos_fabric/nxos_multisite
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check

K8S_CLIENT_RUNTIME="$(pwd -P)/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
export KUBECONFIG="${K8S_CLIENT_RUNTIME}/kubeconfig/config"
hash -r
```

生成物は`k8s_kind/client/runtime/`へ保存され、Git管理しない。k02/k03のcontextを含む
kubeconfigは`runtime/kubeconfig/config`へ作成し、公開ファイルへコピーしない。

実行中のContainerlab topologyにはまだCLI/kubeconfigのbindを追加していない。対象
`adc-t1sv0101`と`bdc-t1sv0104`でのPATH設定、適用条件、YAML追記案は
[`docs/cilium-lab/runbooks/client-tools.md`](../../../docs/cilium-lab/runbooks/client-tools.md)を参照する。

## 構築後のホスト操作

構築後の Containerlab ホストでは、[multisite README の環境変数設定](../../README.md#multisite-client-environment) に従い、
生成済みの k02／k03 管理 API 用 kubeconfig を `KUBECONFIG` に `:` 区切りで指定する。
各 CLI の context を明示し、single-site の同名 k02 context と混在させない。

上記の `runtime/kubeconfig/config` は Fabric client への配置用であり、`prepare-tools.sh` はこのファイルを生成しない。
Fabric endpoint 用 kubeconfig を準備してからそのパスを使用する。
Hubble UI は k02 のみで、SSH／VS Code 転送と k03 の CLI 観測は [アクセス手順](../../README.md#hubble-ui-access) を参照する。
