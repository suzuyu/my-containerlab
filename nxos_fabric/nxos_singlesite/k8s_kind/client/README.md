# Single-site Kubernetes client profile

この profile は single-site lab から Kubernetes API、Cilium、Hubble を確認し、Helm release を管理する
CLI version と Git 管理外 runtime の配置先を定義する。共通準備スクリプトはリポジトリの
`nxos_fabric/scripts/k8s-client/prepare-tools.sh` を使用する。

```bash
cd nxos_fabric/nxos_singlesite
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client
../scripts/k8s-client/prepare-tools.sh --profile k8s_kind/client --check

K8S_CLIENT_RUNTIME="$(pwd -P)/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
export KUBECONFIG="${K8S_CLIENT_RUNTIME}/kubeconfig/config"
hash -r
```

生成物は `k8s_kind/client/runtime/` へ保存され、Git 管理しない。kubeconfig には秘密鍵を含むため、
`runtime/kubeconfig/config` として作成し、公開ファイルへコピーしない。

実行中の Containerlab topology にはまだ CLI／kubeconfig の bind を追加していない。対象
`adc-t1sv0101` での `PATH` 設定、適用条件、YAML 追記案は
[`docs/cilium-lab/client-tools.md`](../../../docs/cilium-lab/client-tools.md)を参照する。

準備スクリプトは `amd64`／`arm64` を判定し、kubectl、Cilium CLI、Hubble CLI、Helm CLI を公式 release URL から
一時 directory へ取得する。公式 SHA256 の検証に合格した binary だけを `runtime/bin/` へ配置する。
