# Network Policy／Tetragon 検証計画

この文書は共通の前提・Manifest 境界と証跡・撤去を扱う。
実行時は [Network Policy 手順](network-policy-test-plan.md) の 4.5 で環境変数を準備し、本書の前提確認後に workload を配置する。
個別試験は [Network Policy：第 4 節](network-policy-test-plan.md) と [Tetragon：第 5 節](tetragon-test-plan.md) を参照する。
節番号・Test ID は分割前の番号を維持している。

## 1. 目的

`adc-k02` の single-site 構築後に、Cilium Network Policy、Hubble、Tetragon を同じ workload で確認する。
通信可否だけでなく、Cilium policy status、Hubble verdict、Tetragon runtime event、resource 使用量を
Test ID で対応付ける。

初期検証は次の境界を守る。

- Policy は `cilium-lab-policy` namespace だけに適用する。
- Clusterwide policy、Host Firewall、Tetragon enforcement は使用しない。
- Tetragon は observe-only とし、host filesystem と credential を観測対象にしない。
- 実行 log、JSON event、packet capture、sysdump は Git 管理外へ保存する。
- manifest は採用 version を固定して review し、remote URL から直接 apply しない。

## 2. 前提条件と試験内 gate

開始前に満たす platform 条件と、4.5 で workload を作成した後に確認する条件を分離する。

| 確認時点 | 項目 | 合格条件 |
|---|---|---|
| 4.5 開始前 | Cilium | 全 Agent／Operator が Ready で、`cilium status --wait` が成功する |
| 4.5 開始前 | Hubble | Relay が Ready で、`hubble status -P` が成功する |
| 4.5 開始前 | Tetragon | DaemonSet が全 Node で Ready である |
| 4.5 開始前 | Resource | 構築後 `MemAvailable` gate を満たし、host と Kind Node container の CPU／memory baseline を記録している |
| base 適用後 | Workload | `deathstar`、`tiefighter`、`xwing`、`tetragon-probe` が Ready になる |
| `NP-00` | Baseline | Policy なしで `tiefighter`／`xwing` から `deathstar` へ到達できる |

開始前の基本確認 command を示す。4.5.1 で対象環境の変数を設定してから実行する。この時点では
`cilium-lab-policy` Namespace は未作成でもよい。

```bash
cilium status --context "${KUBE_CONTEXT}" --wait
hubble status --kube-context "${KUBE_CONTEXT}" -P
kubectl --context "${KUBE_CONTEXT}" -n kube-system rollout status daemonset/tetragon
```

## 3. Manifest 境界

次の Kustomize layer を作成済みである。各 layer は単独で render／diff／apply／rollback できる。

```text
${VALIDATION_ROOT}/
├── network-policy/
│   ├── base/
│   ├── 10-default-deny/
│   ├── 20-dns/
│   ├── 30-l3l4/
│   ├── 40-identity-service-account/
│   ├── 50-fqdn/
│   └── 60-http-l7/
└── tetragon/
    ├── 10-process/
    ├── 20-file/
    ├── 30-network/
    └── 40-privilege/
```

各 layer は `kubectl kustomize`、`kubectl diff -k`、`kubectl apply -k` の順で扱う。複数の Policy layer を
一度に追加せず、各 Test ID の合否と rollback を確認してから次へ進む。

single-site で合格した manifest だけを multi-site の k02／k03 に同期する。現時点では single-site の実 manifest と
runbook を作成済みであり、multi-site 側への同期と running cluster への apply は未実施である。multi-site を選択した
場合は、4.5 の directory 確認を通過するまで apply へ進まない。

## 6. Evidence と rollback

Evidence は topology、日付、cluster ごとに次の Git 管理外 directory へ保存する。

```text
nxos_fabric/<topology>/operations/cilium-lab/<YYYY-MM-DD>/<cluster-name>/
├── README.md
├── SHA256SUMS
└── raw/
```

`README.md` には Test ID／課題 ID、合否、raw file、取得元、未取得証跡を対応付ける。raw file は編集せず、
保存直後に SHA256 を記録する。NX-OS の管理 IP、packet capture、sysdump、JSON event などを含むため、
`operations/` 配下は Git へ追加しない。

2026-08-30 の single-site k02 evidence は、local の
`nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-08-30/adc-k02/` に保存した。

各 Test ID で次を記録する。

- 適用した manifest の render 結果と checksum
- 実行 command、開始／終了時刻、exit code
- workload の応答または timeout
- Hubble flow／verdict
- Tetragon compact／JSON event
- Cilium／Tetragon resource 使用量
- rollback 後の baseline 結果

rollback は次の順序とする。

1. HTTP L7、FQDN、identity、L3/L4、DNS、default-deny の逆順で Policy を削除する。
2. custom TracingPolicy を削除する。
3. validation workload を削除する。
4. `cilium status`、Hubble、`lab-smoke`、LoadBalancer／BGP を再確認する。

## 7. 参照 URL

- [Cilium Network Policy](https://docs.cilium.io/en/stable/security/policy/)
- [Cilium Layer 7 Policy](https://docs.cilium.io/en/stable/security/policy/layer7/)
- [Cilium Star Wars Demo](https://docs.cilium.io/en/stable/gettingstarted/demo/)
- [Hubble Observability](https://docs.cilium.io/en/stable/observability/hubble/)
- [Tetragon Execution Monitoring](https://tetragon.io/docs/getting-started/execution/)
- [Tetragon TracingPolicy](https://tetragon.io/docs/concepts/tracing-policy/)
- [Tetragon Kubernetes filtering](https://tetragon.io/docs/concepts/tracing-policy/k8s-filtering/)
- [Tetragon TracingPolicy reference](https://tetragon.io/docs/reference/tracing-policy/)
