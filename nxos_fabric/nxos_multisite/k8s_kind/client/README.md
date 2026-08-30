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
[`docs/cilium-lab/client-tools.md`](../../../docs/cilium-lab/client-tools.md)を参照する。
