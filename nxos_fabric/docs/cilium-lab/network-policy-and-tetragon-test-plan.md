# Network Policy／Tetragon 検証計画

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

## 4. Network Policy 検証

### 4.1 適用順

1. Policy なしの baseline を記録する。
2. Kubernetes NetworkPolicy で default-deny ingress／egress を適用する。
3. kube-dns への DNS 通信だけを許可する。
4. 必要な L3/L4 通信だけを許可する。
5. CiliumNetworkPolicy で identity／Service Account selector を確認する。
6. FQDN policy を追加する。
7. HTTP L7 policy を追加する。
8. Policy を逆順に削除し、baseline へ戻す。

default-deny egress を適用する前に DNS allow を render しておく。ただし挙動を証明するため、`NP-01` では
default-deny 単体による DNS／通信失敗を短時間だけ確認し、直後に `NP-02` を適用する。

### 4.2 Test matrix

| Test ID | Policy state | Traffic | Expected |
|---|---|---|---|
| `NP-00` | Policy なし | `tiefighter`／`xwing` → `deathstar` | 両方成功し、Hubble で `FORWARDED` |
| `NP-01` | namespace default-deny ingress／egress | 同上と DNS | 新規 connection と DNS が deny され、他 namespace は影響を受けない |
| `NP-02` | DNS allow | kube-dns UDP／TCP `53` | DNS だけ復旧し、application 通信は deny のまま |
| `NP-03` | L3/L4 allow | `tiefighter` → `deathstar` | 指定 port だけ成功し、`xwing` は `DROPPED` |
| `NP-04` | identity／Service Account | selector 一致／不一致 client | 一致する identity だけ成功する |
| `NP-05` | FQDN allow | 許可 FQDN／非許可 FQDN | 許可名だけ成功し、DNS query と policy verdict を照合できる |
| `NP-06` | HTTP L7 allow | 許可 `POST`／path、拒否 `PUT`／path | 許可 request だけ成功し、method／path と L7 verdict を取得できる |
| `NP-07` | 全 Policy 削除 | baseline traffic | `NP-00` と同じ状態へ戻る |

### 4.3 判断 command

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy,ciliumnetworkpolicy
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  describe networkpolicy
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  describe ciliumnetworkpolicy

hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" --since 5m
hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" --verdict DROPPED --since 5m
```

各通信は新規 TCP connection で実行する。Policy 適用前から存在する connection は conntrack により継続する
可能性があるため、新規 connection の結果と分けて記録する。

### 4.4 合格条件

- default-deny の影響が `cilium-lab-policy` namespace 外へ波及しない。
- DNS allow を application allow より先に分離して確認できる。
- Kubernetes NetworkPolicy と CiliumNetworkPolicy の責務差を説明できる。
- Hubble で source、destination、port、verdict、DNS、HTTP method／path を Test ID と対応付けられる。
- Policy 削除後に baseline へ戻り、Cilium LoadBalancer／BGP に regression がない。

### 4.5 具体的な実行手順

#### 4.5.1 対象環境と CLI の選択

repository 内の任意の作業 directory で実行対象を選択する。`TOPOLOGY_PROFILE` と `CLUSTER_NAME` の組み合わせは
次を使用する。

| 実行対象 | `TOPOLOGY_PROFILE` | `CLUSTER_NAME` | `EXTERNAL_TEST_URL` | `CLABNAME` |
|---|---|---|---|---|
| single-site k02 | `nxos_singlesite` | `adc-k02` | `http://172.16.0.2/` | `nxos-fabric-singlesite` |
| multi-site k02 | `nxos_multisite` | `adc-k02` | `http://172.16.0.2/` | `nxos-fabric-multisite` |
| multi-site k03 | `nxos_multisite` | `bdc-k03` | `http://172.16.0.4/` | `nxos-fabric-multisite` |

最初は single-site k02 を選択する。multi-site では先頭の 4 変数だけを上表の値へ変更し、残りは共通で導出する。

```bash
export TOPOLOGY_PROFILE=nxos_singlesite
export CLUSTER_NAME=adc-k02
export EXTERNAL_TEST_URL=http://172.16.0.2/
export CLABNAME=nxos-fabric-singlesite

export REPO_ROOT="$(git rev-parse --show-toplevel)"
export K8S_CLIENT_RUNTIME="${REPO_ROOT}/nxos_fabric/${TOPOLOGY_PROFILE}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
command -v helm kubectl cilium hubble

export CLUSTER_ID="${CLUSTER_NAME##*-}"
export KUBECONFIG="${REPO_ROOT}/nxos_fabric/${TOPOLOGY_PROFILE}/clab-${CLABNAME}/${CLUSTER_NAME}/k8s_kind/${CLUSTER_ID}/kubeconfig-${CLUSTER_ID}"
export KUBE_CONTEXT="kind-${CLUSTER_NAME}"
export POLICY_NS=cilium-lab-policy
export VALIDATION_ROOT="${REPO_ROOT}/nxos_fabric/${TOPOLOGY_PROFILE}/k8s_kind/${CLUSTER_ID}/cilium/manifests/validation"

test -r "${KUBECONFIG}"
test -d "${VALIDATION_ROOT}/network-policy"
test -d "${VALIDATION_ROOT}/tetragon"
printf 'kubeconfig=%s\ncontext=%s\nvalidation=%s\n' \
  "${KUBECONFIG}" "${KUBE_CONTEXT}" "${VALIDATION_ROOT}"
kubectl config get-contexts
kubectl --context "${KUBE_CONTEXT}" get nodes
```

`command -v` でいずれかが表示されない場合は、試験を開始する前に
[クライアントツール準備手順](client-tools.md)で binary cache を準備する。`PATH` の変更は shell ごとの設定なので、
新しい terminal で Hubble を起動する場合も、上記の `PATH` 設定を実行する。

single-site k02 の初期構築、`lab-smoke`、Hubble UI、resource health は確認済みであるため、現在の試験はこの節から
開始できる。multi-site では、対象 cluster の Cilium／Hubble／Tetragon と Cluster Mesh の基本 health を確認してから
同じ手順を実行する。

```bash
cilium status --context "${KUBE_CONTEXT}" --wait
hubble status --kube-context "${KUBE_CONTEXT}" -P
kubectl --context "${KUBE_CONTEXT}" -n kube-system \
  rollout status daemonset/tetragon --timeout=120s
```

#### 4.5.2 base workload の適用

操作用 terminal で base workload を render、client dry-run、差分確認、適用する。base が Namespace と試験
Pod／Service を作成する。初回は Namespace がまだ存在しないため、namespaced resource を含む `kubectl diff -k` は
`NotFound` になる。この場合は静的 render と client dry-run を確認し、初回の server diff だけを省略する。

```bash
kubectl kustomize "${VALIDATION_ROOT}/network-policy/base"
kubectl --context "${KUBE_CONTEXT}" apply \
  --dry-run=client \
  -k "${VALIDATION_ROOT}/network-policy/base"

if kubectl --context "${KUBE_CONTEXT}" get namespace "${POLICY_NS}" \
  >/dev/null 2>&1
then
  kubectl --context "${KUBE_CONTEXT}" diff \
    -k "${VALIDATION_ROOT}/network-policy/base" || {
      rc=$?
      test "${rc}" -eq 1
    }
else
  printf 'INFO: %s is absent; skip the first server diff\n' "${POLICY_NS}"
fi

kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/base"
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" wait \
  --for=condition=Ready pod --all --timeout=120s
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" get pods -o wide
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy,ciliumnetworkpolicy
```

ここで Namespace または Pod が `NotFound`、Pod が `Ready` でない、または Policy resource が残っている場合は
`NP-00` へ進まない。初回の Policy resource は `No resources found` が期待値である。

#### 4.5.3 Hubble CLI と UI の開始

監視用 terminal を開き、4.5.1 の環境変数、`PATH`、`KUBECONFIG` の設定 block を再実行してから Hubble を起動する。
この terminal は以降の Test ID が完了するまで維持する。

```bash
hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" --follow
```

Cilium `1.20.1` の Hubble Relay に対して Hubble CLI `1.19.4` を使用すると、CLI が Relay より古いという warning が
表示される。2026-08-30 時点で [Hubble CLI `v1.19.4`](https://github.com/cilium/hubble/releases/tag/v1.19.4) が
公式最新 release であり、`v1.20.1` の Hubble CLI release は存在しないため、本ラボの固定値は `v1.19.4` を維持する。
warning 自体は不合格にせず、Relay health、flow decode、filter、CLI／UI の一致を確認する。RPC error、未知 field、
filter 不整合が生じた場合は後続試験を止め、利用可能な新しい Hubble CLI release を再確認する。

別の監視用 terminal でも 4.5.1 の設定 block を再実行し、Hubble UI の port-forward を開始する。
試験 server 上で browser を起動せず、local TCP `12000` で待ち受ける。

```bash
cilium hubble ui \
  --context "${KUBE_CONTEXT}" \
  --port-forward 12000 \
  --open-browser=false
```

browser を同じ host で使用する場合は `http://localhost:12000/` を開く。VS Code Remote SSH を使用する場合は、
試験 server の TCP `12000` を local TCP `12000` へ forward してから同じ URL を開く。local port が使用中なら、
コマンドと VS Code の転送先をともに `12001` などへ変更する。

UI で Namespace `cilium-lab-policy` を選択する。flow はこの時点から発生させ、次を Test ID と対応付けて確認する。

| Test ID | UI で確認する内容 |
|---|---|
| `NP-00` | `tiefighter`／`xwing` から `deathstar` への `forwarded` flow と service map |
| `NP-01`～`NP-03` | default-deny の `dropped` と、DNS／L3-L4 allow 後の `forwarded` |
| `NP-04` | Service Account selector の一致／不一致による verdict 差 |
| `NP-06` | HTTP method／path と L7 verdict |
| `NP-07` | rollback 後に baseline の service map と `forwarded` が復旧すること |

UI が空の場合は障害と即断せず、4.5.4 以降の通信を再実行し、画面右上の flow rate と接続 Node 数、CLI の
`hubble observe` を照合する。操作方法と表示項目は
[Cilium 公式 Hubble UI](https://docs.cilium.io/en/stable/observability/hubble/hubble-ui/)を参照する。

#### 4.5.4 `NP-00` Policy なし baseline

操作用 terminal に戻り、`tiefighter` と `xwing` の両方で HTTP status を記録する。

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 3 \
  -X POST http://deathstar/v1/request-landing
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/xwing -- \
  curl -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 3 \
  -X POST http://deathstar/v1/request-landing
```

両方が HTTP `200` で、Hubble が `FORWARDED` を記録した場合にだけ次へ進む。

2026-08-30 の single-site k02 初回結果は次のとおりである。

- Policy resource は `No resources found` であり、Policy なしの状態を確認した。
- `tiefighter` と `xwing` はともに HTTP `200` を返した。
- Hubble CLI で両 client の DNS query と `deathstar:8080/TCP` が `FORWARDED` であることを確認した。
- Hubble UI は `3/3 nodes`、両 client から `deathstar` への service map、TCP `8080`、`forwarded` を表示した。

![NP-00 の Hubble UI 出力例](images/hubble-ui-cilium-lab-policy-np00.png)

*図 4-1: Policy なしで `tiefighter`／`xwing` から `deathstar` へ到達した `NP-00` の出力例*

#### 4.5.5 Policy layer の逐次適用

次に各 layer を 1 つずつ `kubectl diff -k`、`kubectl apply -k` し、表の Test ID を実行する。`NP-01` の適用前に
Service ClusterIP を保存し、DNS 拒否と application 通信拒否を別々に確認する。

##### 4.5.5.1 `NP-01` default-deny

```bash
export DEATHSTAR_CLUSTER_IP="$(kubectl --context "${KUBE_CONTEXT}" \
  -n "${POLICY_NS}" get service deathstar \
  -o jsonpath='{.spec.clusterIP}')"
printf 'deathstar ClusterIP=%s\n' "${DEATHSTAR_CLUSTER_IP}"

kubectl --context "${KUBE_CONTEXT}" diff \
  -k "${VALIDATION_ROOT}/network-policy/10-default-deny"
kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/10-default-deny"
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- getent hosts deathstar
then
  echo 'FAIL: NP-01 expected DNS lookup to be denied'
else
  echo 'PASS: NP-01 DNS lookup was denied'
fi

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 5 \
    -X POST "http://${DEATHSTAR_CLUSTER_IP}/v1/request-landing"
then
  echo 'FAIL: NP-01 expected application traffic to be denied'
else
  echo 'PASS: NP-01 application traffic was denied'
fi
```

2026-08-30 の single-site k02 初回結果は次のとおりで、`NP-01` は合格とした。

- `default-deny-ingress-egress` を作成し、Namespace 内の全 Pod に ingress／egress default-deny を適用した。
- `tiefighter` の DNS lookup は終了 code `2` で拒否された。
- `deathstar` ClusterIP への TCP 接続は HTTP `000`、終了 code `28` で timeout した。
- Hubble は `tiefighter` から CoreDNS `53/UDP` と `deathstar:8080/TCP` の両方を `Policy denied DROPPED` と記録した。

##### 4.5.5.2 `NP-02` DNS allow

`NP-01` の deny を確認した直後に `20-dns` を適用し、DNS だけが復旧して application 通信は拒否されたままに
なることを確認する。

```bash
kubectl --context "${KUBE_CONTEXT}" diff \
  -k "${VALIDATION_ROOT}/network-policy/20-dns"
kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/20-dns"
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- getent hosts deathstar
then
  echo 'PASS: NP-02 DNS lookup recovered'
else
  echo 'FAIL: NP-02 expected DNS lookup to recover'
fi

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 5 \
    -X POST "http://${DEATHSTAR_CLUSTER_IP}/v1/request-landing"
then
  echo 'FAIL: NP-02 application traffic must remain denied'
else
  echo 'PASS: NP-02 application traffic remains denied'
fi

hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" \
  --pod "${POLICY_NS}/tiefighter" \
  --since 5m
```

Hubble で CoreDNS `53/UDP` が `FORWARDED`、`deathstar:8080/TCP` が `DROPPED` である場合に `NP-02` を
合格とする。

2026-08-30 の single-site k02 初回結果は次のとおりで、`NP-02` は合格とした。

- `allow-kube-dns` と `default-deny-ingress-egress` の 2 Policy が適用された。
- `getent hosts deathstar` は Service ClusterIP を返し、DNS lookup の復旧を確認した。
- `deathstar` ClusterIP への TCP 接続は HTTP `000`、終了 code `28` の timeout を維持した。
- Hubble は CoreDNS 2 Pod への UDP `53` を `ALLOWED`／`FORWARDED`、`deathstar:8080/TCP` を
  `Policy denied DROPPED` と記録した。

##### 4.5.5.3 `NP-03` L3／L4 allow

`30-l3l4` を適用し、`tiefighter` の許可と `xwing` の拒否を個別に確認する。

```bash
kubectl --context "${KUBE_CONTEXT}" diff \
  -k "${VALIDATION_ROOT}/network-policy/30-l3l4"
kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/30-l3l4"
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 5 \
    -X POST http://deathstar/v1/request-landing
then
  echo 'PASS: NP-03 tiefighter was allowed'
else
  echo 'FAIL: NP-03 expected tiefighter to be allowed'
fi

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/xwing -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 5 \
    -X POST http://deathstar/v1/request-landing
then
  echo 'FAIL: NP-03 expected xwing to be denied'
else
  echo 'PASS: NP-03 xwing was denied'
fi

hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" \
  --since 5m
```

Hubble で `tiefighter` が `FORWARDED`、`xwing` が `DROPPED` である場合に `NP-03` を合格とする。

2026-08-30 の single-site k02 初回結果は次のとおりで、`NP-03` は合格とした。

- `allow-tiefighter-to-deathstar-ingress` と `allow-tiefighter-to-deathstar-egress` を適用した。
- `tiefighter` から `deathstar` への `POST /v1/request-landing` は HTTP `200` となった。
- `xwing` から同じ endpoint への接続は HTTP `000`、終了 code `28` の timeout となった。
- Hubble は `tiefighter` から `deathstar:8080/TCP` を `ALLOWED`／`FORWARDED`、`xwing` からの同じ通信を
  `Policy denied DROPPED` と記録した。
- `tiefighter` と `xwing` の CoreDNS への UDP `53` はいずれも `ALLOWED`／`FORWARDED` であり、通信結果が
  DNS 拒否によるものではないことを確認した。

##### 4.5.5.4 `NP-04` Service Account identity allow

`NP-04`～`NP-06` は、既存 allow rule との OR 条件で誤判定しないよう、直前の test 用 allow layer を削除してから
次の layer を適用する。`default-deny-ingress-egress` と `allow-kube-dns` は維持する。

`NP-04` では、送信元 Pod の任意 label ではなく Cilium が付与する
`io.cilium.k8s.policy.serviceaccount` identity label を使用する。base manifest では `tiefighter` に
`tiefighter-sa`、`xwing` に `xwing-sa` が設定済みである。まず `NP-03` の L3／L4 allow layer だけを削除し、
残存 Policy と Service Account の割り当てを確認する。

```bash
kubectl --context "${KUBE_CONTEXT}" delete \
  -k "${VALIDATION_ROOT}/network-policy/30-l3l4"

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get pod tiefighter xwing \
  -o custom-columns='NAME:.metadata.name,SERVICE_ACCOUNT:.spec.serviceAccountName'

kubectl --context "${KUBE_CONTEXT}" diff \
  -k "${VALIDATION_ROOT}/network-policy/40-identity-service-account"
kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/40-identity-service-account"

cilium status --context "${KUBE_CONTEXT}" --wait

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get ciliumnetworkpolicy
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  describe ciliumnetworkpolicy \
  allow-tiefighter-service-account-ingress
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  describe ciliumnetworkpolicy \
  allow-tiefighter-service-account-egress
```

期待する残存 Policy は次の 4 つである。

- Kubernetes NetworkPolicy: `default-deny-ingress-egress`、`allow-kube-dns`
- CiliumNetworkPolicy: `allow-tiefighter-service-account-ingress`、
  `allow-tiefighter-service-account-egress`

新規 connection で `tiefighter` の許可と `xwing` の拒否を確認する。

```bash
if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 5 \
    -X POST http://deathstar/v1/request-landing
then
  echo 'PASS: NP-04 tiefighter-sa was allowed'
else
  echo 'FAIL: NP-04 expected tiefighter-sa to be allowed'
fi

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/xwing -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 5 \
    -X POST http://deathstar/v1/request-landing
then
  echo 'FAIL: NP-04 expected xwing-sa to be denied'
else
  echo 'PASS: NP-04 xwing-sa was denied'
fi

for POD in tiefighter xwing; do
  echo "### ${POD}"
  hubble observe --kube-context "${KUBE_CONTEXT}" -P \
    --namespace "${POLICY_NS}" \
    --pod "${POLICY_NS}/${POD}" \
    --since 5m
done
```

`tiefighter` が HTTP `200` かつ Hubble で `FORWARDED`、`xwing` が timeout かつ `DROPPED` である場合に
`NP-04` を合格とする。両 Pod の DNS が `FORWARDED` であることも確認し、名前解決の成否と Service Account
identity による application 通信制御を分けて判定する。

2026-08-30 の single-site k02 初回結果は次のとおりで、`NP-04` は合格とした。

- `tiefighter` と `xwing` に、それぞれ `tiefighter-sa` と `xwing-sa` が割り当てられていることを確認した。
- Service Account identity を選択する 2 つの CiliumNetworkPolicy は、いずれも `VALID=True` となった。
- `tiefighter-sa` から `deathstar` への `POST /v1/request-landing` は HTTP `200` となった。
- `xwing-sa` から同じ endpoint への接続は HTTP `000`、終了 code `28` の timeout となった。
- Hubble は `tiefighter` から `deathstar:8080/TCP` を `ALLOWED`／`FORWARDED`、`xwing` からの同じ通信を
  `Policy denied DROPPED` と記録した。
- 両 Pod の CoreDNS への UDP `53` は `ALLOWED`／`FORWARDED` であり、Service Account identity の不一致が
  application 通信の拒否理由であることを確認した。

##### 4.5.5.5 `NP-05` FQDN allow

`NP-04` の Service Account allow layer を削除してから FQDN layer を適用する。

```bash
kubectl --context "${KUBE_CONTEXT}" delete \
  -k "${VALIDATION_ROOT}/network-policy/40-identity-service-account"

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy,ciliumnetworkpolicy

kubectl --context "${KUBE_CONTEXT}" diff \
  -k "${VALIDATION_ROOT}/network-policy/50-fqdn"
kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/50-fqdn"

cilium status --context "${KUBE_CONTEXT}" --wait

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get ciliumnetworkpolicy
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  describe ciliumnetworkpolicy allow-tiefighter-example-fqdn
```

期待する残存 Policy は次の 3 つである。

- Kubernetes NetworkPolicy: `default-deny-ingress-egress`、`allow-kube-dns`
- CiliumNetworkPolicy: `allow-tiefighter-example-fqdn`

初期 manifest は次の 2 つの egress rule を持つ。

- 信頼する cluster DNS である `kube-system/kube-dns` の port `53` だけを Cilium DNS Proxy へ転送し、
  `matchPattern: "*"` で query を許可・観測する。
- 観測した DNS 応答のうち、`www.example.com` に対応する IP の TCP `80` だけを許可する。

標準 Kubernetes NetworkPolicy の L4 DNS allow だけでは、`toFQDNs` が必要とする DNS 応答の観測と IP cache への
登録を行えない。CiliumNetworkPolicy の `rules.dns` を別 rule として明示する必要がある。詳細は Cilium 公式の
[DNS Policy and IP Discovery](https://docs.cilium.io/en/stable/security/policy/layer7/#dns-policy-and-ip-discovery) と
[Locking Down External Access with DNS-Based Policies](https://docs.cilium.io/en/stable/security/dns/) を参照する。

外部 FQDN の試験前に、CoreDNS upstream が Pod から到達可能であることを確認する。resolver の優先順位は
`--upstream`、`COREDNS_UPSTREAM_DNS`、Containerlab host の `/etc/resolv.conf` にある最初の非 loopback
IPv4 nameserver の順である。環境固有値は manifest へ記載せず、site 別の Git 管理外 runtime file へ保存する。

まず check-only で選定値と CoreDNS の差分を表示する。

```bash
export COREDNS_RUNTIME="${REPO_ROOT}/nxos_fabric/${TOPOLOGY_PROFILE}/k8s_kind/${CLUSTER_ID}/cilium/runtime/20-coredns-upstream.env"

"${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/configure-coredns-upstream.sh" \
  --context "${KUBE_CONTEXT}" \
  --record "${COREDNS_RUNTIME}"
```

自動検出値を利用しない環境では、実行 shell だけに resolver を指定して再確認する。

```bash
export COREDNS_UPSTREAM_DNS="<Pod から到達可能な resolver IPv4>"

"${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/configure-coredns-upstream.sh" \
  --context "${KUBE_CONTEXT}" \
  --record "${COREDNS_RUNTIME}"
```

表示された resolver が対象環境の値であることを確認してから適用する。

```bash
"${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/configure-coredns-upstream.sh" \
  --context "${KUBE_CONTEXT}" \
  --record "${COREDNS_RUNTIME}" \
  --apply

kubectl --context "${KUBE_CONTEXT}" -n kube-system \
  get configmap coredns -o jsonpath='{.data.Corefile}' | \
  grep 'forward \.'
```

スクリプトは採用 resolver への Pod 直達試験、CoreDNS ConfigMap patch、CoreDNS rollout、Cluster DNS
試験を順に実施する。適用後の Cluster DNS 試験に失敗した場合は元の Corefile へ rollback する。CoreDNS の
`forward` 変更は Kubernetes 公式の
[Customizing DNS Service](https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/) に基づく。
課題の診断記録は [`TI-003`](test-issue-register.md#6-ti-003-kind-上の-coredns-upstream-到達不可)を参照する。

非許可側には同じ DNS／HTTP 条件で比較できる `www.example.net` を使用する。両方の DNS 応答が得られることを先に
確認してから、IPv4 HTTP 到達性を比較する。

```bash
export FQDN_ALLOW="www.example.com"
export FQDN_DENY="www.example.net"

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tiefighter -- \
  getent hosts "${FQDN_ALLOW}"
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tiefighter -- \
  getent hosts "${FQDN_DENY}"
```

いずれかの外部 FQDN が解決できない場合は HTTP 判定へ進まず、内部 DNS と FQDN Policy の対象外 Pod を使って
障害境界を確認する。

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  getent hosts kubernetes.default.svc.cluster.local

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tetragon-probe -- \
  getent hosts "${FQDN_ALLOW}"

kubectl --context "${KUBE_CONTEXT}" -n kube-system \
  logs -l k8s-app=kube-dns \
  --prefix --since=10m --tail=200
```

- 内部 DNS も失敗する場合は、Pod → CoreDNS Service の経路を切り分ける。
- 内部 DNS は成功し、`tiefighter` と `tetragon-probe` の外部 DNS がともに失敗する場合は、CoreDNS upstream を
  切り分ける。
- `tetragon-probe` は成功し、`tiefighter` だけが失敗する場合は、Cilium DNS Proxy rule、Agent log、FQDN cache を
  切り分ける。

両外部 FQDN の DNS gate を通過したら HTTP 通信を確認する。

```bash

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  curl -4 -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 10 \
    "http://${FQDN_ALLOW}/"
then
  echo 'PASS: NP-05 allowed FQDN was reachable'
else
  echo 'FAIL: NP-05 expected the allowed FQDN to be reachable'
fi

if kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  exec pod/tiefighter -- \
  curl -4 -sS -o /dev/null -w '%{http_code}\n' \
    --connect-timeout 3 --max-time 10 \
    "http://${FQDN_DENY}/"
then
  echo 'FAIL: NP-05 expected the non-allowed FQDN to be denied'
else
  echo 'PASS: NP-05 non-allowed FQDN was denied'
fi

hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" \
  --pod "${POLICY_NS}/tiefighter" \
  --since 5m

export FQDN_TEST_NODE="$(kubectl --context "${KUBE_CONTEXT}" \
  -n "${POLICY_NS}" get pod tiefighter \
  -o jsonpath='{.spec.nodeName}')"
export FQDN_CILIUM_POD="$(kubectl --context "${KUBE_CONTEXT}" \
  -n kube-system get pod -l k8s-app=cilium \
  --field-selector "spec.nodeName=${FQDN_TEST_NODE}" \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl --context "${KUBE_CONTEXT}" -n kube-system \
  exec "${FQDN_CILIUM_POD}" -- \
  cilium-dbg fqdn cache list | grep -E 'www\.example\.(com|net)' || true
```

両 FQDN の名前解決が成功し、許可 FQDN の HTTP 通信だけが成功する場合に `NP-05` を合格とする。Hubble では
CoreDNS への DNS flow、許可先への `FORWARDED`、非許可先への `DROPPED` を照合し、Cilium Agent の FQDN cache に
許可 FQDN と応答 IP が登録されていることを確認する。DNS 応答が得られない場合や許可先自体が停止している場合は
Policy の合否にせず、外部到達性の前提不成立として切り分ける。FQDN cache の確認 command は Cilium 公式の
[`cilium-dbg fqdn cache list`](https://docs.cilium.io/en/stable/cmdref/cilium-dbg_fqdn_cache_list/) に基づく。

2026-08-30 の single-site k02 初回試行は、次の理由により `NP-05` を判定保留とした。

- `allow-tiefighter-example-fqdn` の validation は成功し、`VALID=True` となった。
- Pod から CoreDNS への UDP `53` は Hubble で `ALLOWED`／`FORWARDED` だった。
- 許可・非許可 FQDN の両方で `getent hosts` が終了 code `2`、`curl` が `Resolving timed out` となった。
- 非許可 FQDN の timeout も DNS 解決失敗によるため、FQDN Policy による拒否とは判定しなかった。
- 初回 manifest で不足していた Cilium DNS Proxy の `rules.dns` を追加し、CNP が `VALID=True` になることを
  確認したが、外部名の解決は復旧しなかった。
- 内部 Service DNS は成功し、Policy 対象の `tiefighter` と対象外 Pod の外部 DNS はともに失敗した。
- CoreDNS log では Node 内の Docker embedded DNS への query timeout／connection refused が観測された。
- 一時 Pod で `dnsPolicy: None` と host resolver を直接指定すると `www.example.com` の AAAA 応答が得られた。
  このため障害境界を CoreDNS upstream と判断し、上記の共通スクリプトで runtime 設定してから再試験する。
- 同日、runtime resolver の check-only と `--apply` を実行し、Pod 直達試験と Cluster DNS 試験がともに成功した。
  CoreDNS の `forward` 変更と site 別 runtime record の作成は完了し、`NP-05` の通信判定から再開できる。
- 許可対象と非許可対象の両 FQDN の名前解決が成功した状態で、許可対象は HTTP `200`、非許可対象は
  HTTP `000`／終了 code `28` の timeout となった。
- Hubble では両 FQDN の A／AAAA query と応答が `FORWARDED`、許可対象の TCP `80` が
  `ALLOWED`／`FORWARDED`、非許可対象の TCP SYN が `Policy denied DROPPED` となった。
- Pod の resolver search と `ndots` により、外部名へ cluster domain suffix を付加した中間 query は
  `Non-Existent Domain` となったが、最終的な絶対名の A／AAAA query は正常応答しており、不合格にはしない。
- `tiefighter` と同じ Node の Cilium Agent FQDN cache に、両 FQDN の A／AAAA 応答と TTL が登録された。
- DNS、通信結果、Hubble verdict、FQDN cache が期待値と一致したため、`NP-05` を合格とする。

##### 4.5.5.6 `NP-06` HTTP L7 allow

`NP-05` の FQDN layer を削除してから HTTP L7 layer を適用する。許可する `POST` と拒否する `PUT` は、
既存 connection の再利用を避けて別々の `curl` process で比較する。

```bash
kubectl --context "${KUBE_CONTEXT}" delete \
  -k "${VALIDATION_ROOT}/network-policy/50-fqdn"
kubectl --context "${KUBE_CONTEXT}" apply \
  -k "${VALIDATION_ROOT}/network-policy/60-http-l7"
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 3 \
  -X POST http://deathstar/v1/request-landing
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tiefighter -- \
  curl -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 3 \
  -X PUT http://deathstar/v1/request-landing
```

各 apply 後に `kubectl describe` と Hubble の `FORWARDED`／`DROPPED` を保存する。`NP-07` では逆順に
Policy layer を削除し、最後に `NP-00` と同じ 2 command が成功することを確認する。

2026-08-30 の single-site k02 では、2 つの CiliumNetworkPolicy がともに `VALID=True` となり、
`tiefighter` の `POST /v1/request-landing` は HTTP `200`、同じ path の `PUT` は HTTP `403` となった。
Hubble では POST request と HTTP `200` response が `FORWARDED`、PUT request が `DROPPED`、HTTP `403`
response が `FORWARDED` と記録された。非対象 `xwing` の POST は HTTP `000`／終了 code `28` の timeout となった。
method、path、source selector と Hubble L7 event が期待値に一致したため、`NP-06` を合格とする。

##### 4.5.5.7 `NP-07` Policy rollback と baseline 復旧

`NP-06` の確認後、L7、DNS、default-deny の逆順で Policy layer を削除する。削除対象を一括指定せず、各 layer の
resource が削除されたことを command 出力で確認する。

```bash
kubectl --context "${KUBE_CONTEXT}" delete \
  -k "${VALIDATION_ROOT}/network-policy/60-http-l7"

kubectl --context "${KUBE_CONTEXT}" delete \
  -k "${VALIDATION_ROOT}/network-policy/20-dns"

kubectl --context "${KUBE_CONTEXT}" delete \
  -k "${VALIDATION_ROOT}/network-policy/10-default-deny"

kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get networkpolicy,ciliumnetworkpolicy
```

`No resources found` を確認してから、`NP-00` と同じ 2 client の baseline traffic を再実行する。

```bash
for POD in tiefighter xwing; do
  printf '### %s\n' "${POD}"

  kubectl --context "${KUBE_CONTEXT}" \
    -n "${POLICY_NS}" exec "pod/${POD}" -- \
    curl -sS -o /dev/null -w '%{http_code}\n' \
      --connect-timeout 3 --max-time 5 \
      -X POST http://deathstar/v1/request-landing
done
```

両方が HTTP `200` となることを合格条件とする。Policy 削除後は Envoy の HTTP L7 visibility 対象外になるため、
`hubble observe --protocol http` に新しい baseline request が表示されない場合がある。rollback 前の event と
混同しないよう、新規 request を発生させた直後に protocol filter なしで TCP flow を確認する。

```bash
for POD in tiefighter xwing; do
  kubectl --context "${KUBE_CONTEXT}" \
    -n "${POLICY_NS}" exec "pod/${POD}" -- \
    curl -sS -o /dev/null --connect-timeout 3 --max-time 5 \
      -X POST http://deathstar/v1/request-landing
done

hubble observe \
  --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" \
  --since 1m
```

最後に Cilium と BGP Control Plane が Policy rollback の影響を受けていないことを確認する。

```bash
cilium status --context "${KUBE_CONTEXT}" --wait
cilium bgp peers --context "${KUBE_CONTEXT}"
```

2026-08-30 の single-site k02 では、全 NetworkPolicy／CiliumNetworkPolicy の削除後に `No resources found` を
確認し、`tiefighter` と `xwing` の POST はともに HTTP `200` へ復旧した。Cilium／Operator／Envoy／Hubble は
Ready、worker 2 Node から ADC BGR 2 台への IPv4／IPv6 BGP session はすべて `established` であった。
protocol filter なしの Hubble では、両 Pod の DNS flow と `deathstar:8080` の TCP handshake、request／response、
connection close がすべて `FORWARDED` となった。baseline、観測、platform health が期待値に一致したため、
`NP-07` を合格とする。

### 4.6 Single-site k02 結果一覧

| Test ID | 結果 | 主な確認内容 |
|---|---|---|
| `NP-00` | 合格 | Policy なしで `tiefighter`／`xwing` が HTTP `200` |
| `NP-01` | 合格 | default-deny で DNS と application traffic を拒否 |
| `NP-02` | 合格 | CoreDNS 通信だけ復旧し、application traffic は拒否を維持 |
| `NP-03` | 合格 | `tiefighter` の L3/L4 通信だけ許可し、`xwing` を拒否 |
| `NP-04` | 合格 | Service Account identity 一致だけ許可 |
| `NP-05` | 合格 | FQDN の DNS 観測、許可先通信、非許可先拒否、FQDN cache を確認 |
| `NP-06` | 合格 | HTTP POST を許可し、PUT を L7 で拒否、非対象 source を拒否 |
| `NP-07` | 合格 | 全 Policy を削除し、baseline traffic、Hubble、Cilium／BGP health が復旧 |

`NP-00` から `NP-07` まで全項目が合格したため、single-site k02 の Network Policy 試験系列を完了とする。

## 5. Tetragon 検証

### 5.1 適用順

1. custom TracingPolicy なしで built-in process execution event を確認する。
2. namespace、Pod label、binary selector を持つ process policy を追加する。
3. test Pod の `/tmp/tetragon-lab-*` だけを対象とする file policy を追加する。
4. test Pod の `tcp_connect`／`tcp_close` event を観測する network policy を追加する。
5. lab 専用 Pod だけを対象とする privilege policy を追加する。
6. policy なし、限定 policy、event load の resource／event drop を比較する。
7. Tetragon の停止／再開中に Cilium 通信が継続することを確認する。

TracingPolicy の hook、argument index、selector は低水準の kernel ABI に依存する。採用する Tetragon
version の公式 policy library／例を取得し、hook と argument の意味を review してから local manifest として
保存する。独自の推測だけで `kprobe`／`tracepoint` policy を作成しない。

### 5.2 Test matrix

| Test ID | Action | Expected |
|---|---|---|
| `TG-00` | `xwing` 内で shell → `curl` | `process_exec`／`process_exit`、parent、arguments、Pod metadata |
| `TG-01` | 対象／非対象 namespace で同じ process を実行 | 対象 namespace の event だけを policy が選択する |
| `TG-02` | `emptyDir` の `/tmp/tetragon-lab-write` へ write | write event と Pod metadata を取得し、他 path の noise を抑制する |
| `TG-03` | 同じ `/tmp/tetragon-lab-write` を read | read event と Pod metadata を取得する |
| `TG-04` | test Pod → 外部 HTTP server | `tcp_connect`／`tcp_close` event と Hubble flow の timestamp／5-tuple が一致する |
| `TG-05` | lab 専用 Pod で失敗する `chown` を実行 | `cap_capable` event を observe-only で取得し、host process は対象外になる |
| `TG-06` | 短時間の event load | CPU、memory、event drop の増分が記録される |
| `TG-07` | Tetragon DaemonSet 停止／再開 | Cilium CNI、ClusterIP、LoadBalancer 通信が継続する |
| `TG-08` | TracingPolicy 削除 | custom event が停止し、built-in event と Cilium 通信が継続する |

### 5.3 Event 取得

最初は compact output で event 形状を確認し、証拠保存時だけ JSON を Git 管理外へ出力する。

3 Node 環境では、観測対象 workload と同じ Node 上の Tetragon Pod を選ぶ。DaemonSet 名を直接指定すると、
別 Node の Tetragon Pod が選択される可能性があるため使用しない。

```bash
export TARGET_POD=xwing
export TARGET_NODE="$(kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" \
  get pod "${TARGET_POD}" -o jsonpath='{.spec.nodeName}')"
export TETRAGON_POD="$(kubectl --context "${KUBE_CONTEXT}" -n kube-system \
  get pods -l app.kubernetes.io/name=tetragon \
  --field-selector "spec.nodeName=${TARGET_NODE}" \
  -o jsonpath='{.items[0].metadata.name}')"

test -n "${TETRAGON_POD}"
kubectl --context "${KUBE_CONTEXT}" -n kube-system exec \
  "${TETRAGON_POD}" -c tetragon -- \
  tetra getevents -o compact --pods "${TARGET_POD}"

kubectl --context "${KUBE_CONTEXT}" get \
  tracingpolicies.cilium.io,tracingpoliciesnamespaced.cilium.io --all-namespaces
kubectl --context "${KUBE_CONTEXT}" -n kube-system logs \
  daemonset/tetragon -c tetragon --since=10m
```

`tetra getevents` は試験時間だけ起動し、Pod で event を発生させた時刻を別 terminal で記録する。argument に
token、password、kubeconfig、Secret の内容を渡さない。

### 5.4 Hubble との照合

`TG-04` では Tetragon event と Hubble flow を次の項目で照合する。

| Field | Tetragon | Hubble |
|---|---|---|
| Workload | namespace、Pod、container | namespace、Pod、identity |
| Process | binary、arguments、parent | 原則対象外 |
| Network | source／destination address、port | source／destination、port、verdict |
| Time | event timestamp | flow timestamp |

同じ HTTP request に固有の request ID を header へ付け、外部 server log も同じ Test ID へ対応付ける。

### 5.5 Resource／failure safety

```bash
free -m
docker stats --no-stream \
  "${CLUSTER_NAME}-control-plane" \
  "${CLUSTER_NAME}-worker" \
  "${CLUSTER_NAME}-worker2"
cilium status --context "${KUBE_CONTEXT}" --wait
cilium connectivity test --context "${KUBE_CONTEXT}"
```

Metrics Server を別途導入した場合だけ、補助情報として
`kubectl --context "${KUBE_CONTEXT}" top pods -n kube-system --containers` を使用する。初期構築の resource
判定を Metrics Server の存在へ依存させない。

`TG-07` の DaemonSet 停止／再開は cluster state を変更するため、対象 cluster と実施操作についてユーザー承認を
得てから行う。停止前、停止中、復旧後に同じ connectivity test と `lab-smoke` traffic を実行する。

### 5.6 合格条件

- process、file、network、privilege event を namespace／Pod metadata と関連付けられる。
- selector 対象外の event が抑制され、host process や credential を収集しない。
- network event と Hubble flow を timestamp、Pod、5-tuple で対応付けられる。
- idle と短時間 load の CPU／memory 増分、event drop を記録できる。
- Tetragon 停止／再開中も Cilium datapath と Service 通信が継続する。
- custom TracingPolicy を削除して observe-only baseline へ戻せる。

### 5.7 具体的な実行手順

`TG-00` は 5.3 の event stream を 1 つ目の terminal で起動し、2 つ目の terminal で process event を発生させる。

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/xwing -- \
  sh -c 'curl -sS --connect-timeout 3 http://deathstar/ >/dev/null'
```

compact event で `process_exec`、`process_exit`、Pod、binary、arguments、parent を確認する。完全な JSON は
`-o compact` を外して Git 管理外の evidence directory へ保存する。

`TG-01` 以降は公式 policy library と採用 version を確認して local manifest に保存し、次の順で適用する。

```bash
export TETRAGON_ROOT="${VALIDATION_ROOT}/tetragon"

kubectl kustomize "${TETRAGON_ROOT}/10-process"
kubectl --context "${KUBE_CONTEXT}" diff -k "${TETRAGON_ROOT}/10-process"
kubectl --context "${KUBE_CONTEXT}" apply -k "${TETRAGON_ROOT}/10-process"

kubectl --context "${KUBE_CONTEXT}" diff -k "${TETRAGON_ROOT}/20-file"
kubectl --context "${KUBE_CONTEXT}" apply -k "${TETRAGON_ROOT}/20-file"

kubectl --context "${KUBE_CONTEXT}" diff -k "${TETRAGON_ROOT}/30-network"
kubectl --context "${KUBE_CONTEXT}" apply -k "${TETRAGON_ROOT}/30-network"

kubectl --context "${KUBE_CONTEXT}" diff -k "${TETRAGON_ROOT}/40-privilege"
kubectl --context "${KUBE_CONTEXT}" apply -k "${TETRAGON_ROOT}/40-privilege"
```

file event は専用 Pod の `emptyDir` だけで発生させる。

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tetragon-probe -- \
  sh -c 'printf tetragon-lab > /tmp/tetragon-lab-write && read_value=$(cat /tmp/tetragon-lab-write) && test "${read_value}" = tetragon-lab'
```

privilege event は専用 path に対する `chown` を非 privileged Pod から実行する。command が成功することを
合格条件にせず、`Operation not permitted` と対応する `cap_capable` event が得られることを確認する。

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tetragon-probe -- \
  sh -c 'if chown 0:0 /tmp/tetragon-lab-write; then exit 1; else exit 0; fi'
```

network event は request ID を付けて外部 server へ送信し、同時に Hubble flow を取得する。

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${POLICY_NS}" exec pod/tetragon-probe -- \
  curl -sS --connect-timeout 3 -H 'X-Lab-Test-ID: TG-04' "${EXTERNAL_TEST_URL}"
hubble observe --kube-context "${KUBE_CONTEXT}" -P \
  --namespace "${POLICY_NS}" --since 2m
```

`TG-06` の前後で `docker stats --no-stream` と Tetragon metrics／log の event drop を記録する。`TG-07` は
明示的な承認後だけ実行する。最後に `40-privilege`、`30-network`、`20-file`、`10-process` の逆順で削除し、
custom event の停止と Cilium connectivity の継続を確認する。

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
