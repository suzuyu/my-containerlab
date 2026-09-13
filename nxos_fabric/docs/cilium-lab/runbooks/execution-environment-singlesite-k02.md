# 実際の試験環境：single-site k02

この文書は single-site `adc-k02` の実行ホスト、配置パス、環境変数、転送方法をまとめる。
試験の操作・判定は [Egress Gateway 共通手順](../tests/egress-gateway-test-plan.md)、
進捗は [現在のステータス](../status.md) を参照する。
2026-09-06〜13 の準備・実施履歴は [日付付きの環境記録](../results/singlesite/2026-09-12/execution-environment-history-2026-09-12.md) に保存する。

別環境で流用するときは、この環境メモを複製して値を変更し、手順へ渡す環境変数を設定する。
個人のユーザー名やホームディレクトリは、共通手順の前提にしない。

## 1. ホストの役割と配置

| 項目 | 今回の値・運用 |
|---|---|
| ラボ実行ホスト | `clab01`、管理 IP `192.168.129.59` |
| SSH 接続 | `suzuyu@192.168.129.59`。登録済み鍵による認証を使用する |
| 端末 A／B | どちらも `clab01` に接続した shell。実行ホスト上の同じファイルと Docker 環境を使う |
| 実行ホストのリポジトリ | `/home/suzuyu/containerlab` |
| ローカル作業環境のリポジトリ | `/home/suzuyu/my-containerlab` |
| topology | `nxos_singlesite` |
| cluster／context | `adc-k02`／`kind-adc-k02` |
| CLI 配置 | 実行リポジトリ配下の `nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin` |
| コードの配布 | ファイルを直接転送する。実行サーバの Git 同期は前提にしない |
| 証跡 | 実行ホストに保存し、確定後にローカル作業環境へ転送する |

SSH 秘密鍵、token、kubeconfig の認証データはこの文書へ記載しない。
同じラボ内の Gateway Node 名・IP 割り当ては [アドレス台帳](../design/parameter-and-address-allocation.md#5-egress-gateway) で管理する。

<a id="environment-variables"></a>

## 2. 環境変数

**端末 A／B のそれぞれで、clab01 に接続した後に実行する。**
このブロックは今回の配置先に対応する設定であり、試験 resource は変更しない。

```bash
export REPO_ROOT=/home/suzuyu/containerlab
export KUBE_CONTEXT=kind-adc-k02
# 新規セッションの記録日。継続時は保存済み session.env の TEST_DATE を使う。
export TEST_DATE="$(date +%F)"
export KUBECONFIG="${REPO_ROOT}/nxos_fabric/nxos_singlesite/clab-nxos-fabric-singlesite/adc-k02/k8s_kind/k02/kubeconfig-k02"
```

その後、[共通手順 2：環境設定と証跡](../tests/egress-gateway-test-plan.md#egress-session) へ戻る。
端末 B で試験セッションを作り、両端末で読み込む。
CLI の `PATH`、試験日の `TEST_DATE`、証跡先の `EG_DIR` は手順内で設定・保存する。

## 3. コード配置と証跡転送

Egress Gateway 試験前に、次のファイルをローカル作業環境から実行ホストの同じ相対パスへ転送する。
手順だけ新しく、manifest／スクリプトが古い状態で実施しない。

- `nxos_fabric/docs/cilium-lab/tests/` 配下の Egress 共通・基本機能・異常系・性能手順
- `nxos_fabric/docs/cilium-lab/design/egress-gateway-routed-design.md`
- `nxos_fabric/nxos_singlesite/configs/changes/cilium-stage2b/` 配下
- `nxos_fabric/docs/cilium-lab/runbooks/execution-environment-singlesite-k02.md`
- `nxos_fabric/nxos_singlesite/k8s_kind/k02/cilium/manifests/validation/egress/` 配下
- `nxos_fabric/scripts/cilium-lab/configure-egress-gateway-addresses.sh`
- `nxos_fabric/scripts/cilium-lab/configure-egress-interface-init.sh`
- `nxos_fabric/scripts/cilium-lab/converge-cilium-lab.sh`
- `nxos_fabric/nxos_singlesite/k8s_kind/k02/cilium/manifests/egress-interface-init/` 配下

今回の証跡パスの対応は以下のとおり。`<TEST_DATE>` と `<session>` は手順で実際に生成した値を使う。
日付をまたいでも、端末 A で新しい日付を計算して別セッションへ変更しない。

| 保存場所 | パス |
|---|---|
| 実行ホスト | `/home/suzuyu/containerlab/nxos_fabric/nxos_singlesite/operations/cilium-lab/<TEST_DATE>/adc-k02/raw/<session>/` |
| 転送後のローカル作業環境 | `/home/suzuyu/my-containerlab/nxos_fabric/nxos_singlesite/operations/cilium-lab/<TEST_DATE>/adc-k02/raw/<session>/` |

端末 A の外部サーバログ保存と後片付けまで終わってから `SHA256SUMS` を確定し、セッションディレクトリ全体を転送する。
転送後はそのディレクトリ内で `sha256sum -c SHA256SUMS` を実行する。
共通手順の相対パス方式により、実行側とローカル側でリポジトリの絶対パスが違っていても照合できる。
`operations/` 配下の証跡は Git へ追加しない。

<a id="egress-probe-build"></a>

## 4. 追加測定用バイナリの準備・配布

実行ホストに Go がない場合は、Linux amd64 の測定バイナリを作業環境で作り、転送する。
[ソース](../../../scripts/cilium-lab/egress-probe.go) とバイナリ、使用した Go の版・ハッシュを実行セッションへ保存する。
以前のバイナリのハッシュを再利用せず、今回ビルドしたものを照合する。

**準備用の作業端末（ローカル）：** Go を使える環境で実行する。この準備だけは実行ホストの端末 A／B と区別する。

```bash
(
  set -euo pipefail
  cd /home/suzuyu/my-containerlab
  command -v go
  probe_build="$(mktemp -d /tmp/egress-probe-build-XXXXXXXX)"
  go version > "$probe_build/go-version.log"
  cp nxos_fabric/scripts/cilium-lab/egress-probe.go "$probe_build/"
  CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GO111MODULE=off go build -o "$probe_build/egress-probe" "$probe_build/egress-probe.go"
  (cd "$probe_build" && sha256sum egress-probe.go egress-probe go-version.log > SHA256SUMS)
  scp "$probe_build/egress-probe" suzuyu@192.168.129.59:/home/suzuyu/containerlab/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin/egress-probe
  scp "$probe_build/egress-probe.go" suzuyu@192.168.129.59:/home/suzuyu/containerlab/nxos_fabric/scripts/cilium-lab/egress-probe.go
  printf 'build=%s\n' "$probe_build"
  cat "$probe_build/SHA256SUMS"
)
```

**端末 B（clab01）：** 次のハッシュを準備側の同名ファイルと照合してから、[基本機能手順 12.5](../tests/egress-gateway-functional-tests.md#egress-pod-delay) へ進む。

```bash
sha256sum \
  "$REPO_ROOT/nxos_fabric/scripts/cilium-lab/egress-probe.go" \
  "$REPO_ROOT/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin/egress-probe"
"$REPO_ROOT/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin/egress-probe" help
```
