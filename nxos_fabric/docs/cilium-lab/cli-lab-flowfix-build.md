# Cilium CLI 検証用修正版の取得・パッチ適用・ビルド手順

## 1. 目的と位置付け

公式 Cilium CLI `v0.19.7` に、本ラボの `connectivity test` の期待条件を修正するパッチを適用し、
`v0.19.7-lab-flowfix.3` をビルドする。`lab-flowfix.3` は本ラボで付けた識別名であり、公式リリースではない。
対象は **試験を実行・判定する CLI**。クラスタ内の Cilium Agent や BPF のビルド手順ではない。

ここでいう公式ソースの pull は、再現性のため `v0.19.7` を指定した `git clone` で行う。
新規作業ディレクトリに取得するので、この containerlab リポジトリや実行サーバを Git 同期する必要はない。
標準 `cilium` の上書き・クラスタへの接続・試験 Policy の適用は、このビルド手順では行わない。

取得・適用するものは次のとおり。

| 項目 | 固定値・参照先 |
|---|---|
| 公式リポジトリ | `https://github.com/cilium/cilium-cli.git` |
| 取得タグ | `v0.19.7` |
| タグが指すコミット | `7ca7fc53c20275f5c10ef5f3557076691fd1d720` |
| 適用する全差分 | [v0.19.7-lab-flowfix.3.patch](cli-lab-flowfix/v0.19.7-lab-flowfix.3.patch) |
| 元ソースの照合 | [UPSTREAM.SHA256SUMS](cli-lab-flowfix/UPSTREAM.SHA256SUMS)：変更対象の既存ファイルと依存関係定義、計 8 ファイル |
| 適用後の照合 | [PATCHED.SHA256SUMS](cli-lab-flowfix/PATCHED.SHA256SUMS)：修正・追加した Go コード、計 10 ファイル |
| 由来・参考バイナリのハッシュ | [provenance.json](cli-lab-flowfix/provenance.json) |
| ライセンス | 公式ソースの [Apache License 2.0](cli-lab-flowfix/LICENSE)。元コードの著作権・ライセンス表記を保持する |

パッチには変更コードと追加の単体テストを含む。`.1` → `.2` → `.3` を個別に適用する必要はなく、
**未変更の公式 `v0.19.7` に、この全差分を 1 回だけ適用する**。
実行ログ・kubeconfig・認証情報・ビルド済みバイナリは、この文書ディレクトリに含めない。

文書整備時の新規取得からの再現確認で、旧試験記録の保存パッチには `check/service_flow.go` が
不足していることが分かった。本書のパッチには元のビルドソースに存在する同ファイルを補完した。
検証済みバイナリのロジックを追加変更したものではなく、再現に必要なコードを揃えたものである。
再作成時は本書に同梱する全差分を使用する。

## 2. 何を修正しているか

| 追加した段階 | 問題と修正内容 | 維持する確認 |
|---|---|---|
| `.1` | IP 直指定の Service に不要な DNS 要求を除去。Service selector / namespace / family に対応する具体的な backend IP を照合先へ追加。NodePort の action に実際の宛先 family を設定 | TCP ポート、SYN / FIN、許可・拒否。無関係な宛先を許容する wildcard は追加しない |
| `.2` | 自己宛 Service を curl 成功と対象 PRE socket event で判定。HTTP proxy を使わない FQDN 試験から HTTP event・パス制御の期待を除去 | 対象 Pod / Service の照合、drop / RST の拒否。FQDN の DNS / TCP / drop と curl 判定。HTTP ルールを持つ他の試験の HTTP 要求 |
| `.3` | aggregation 有効時に自己宛 curl の直前で 6 秒待機し、CLI の準備通信と間隔を空ける | 欠落 event を合格にする条件は追加しない。失敗した curl を再試行して成功扱いにしない |

修正対象は取得したソースの `vendor/github.com/cilium/cilium/cilium-cli/connectivity/` 配下にある。
CLI の依存先である Cilium 側の connectivity 実装が vendor に含まれるため、この場所を修正する。

| ファイル | 役割 |
|---|---|
| `tests/service.go` | Service / NodePort / 自己宛 Service の試験実行と要求する flow |
| `check/check.go`、`check/action.go` | 具体的な代替宛先の照合、自己宛の禁止 flow を後続 event への再照合で無視しない処理 |
| `check/self_service.go` | 対象 Pod / Service の PRE socket event を照合する追加コード |
| `check/service_flow.go` | Service selector / namespace / family に一致する backend IP を選ぶ補助コード |
| `filters/filters.go` | 自己宛で禁止 flow の観測を確定失敗にする指定を追加 |
| `builder/to_fqdns.go` | HTTP proxy を使わない FQDN Policy に対応する期待条件 |
| `check/service_flow_test.go`、`check/self_service_test.go`、`builder/to_fqdns_lab_test.go` | 修正の単体テスト |

### 自己宛 Service の判定と制約

対象 namespace / Pod 名 / Pod IP / Service 名 / VIP / TCP port / family が一致する
`SOCK` / `TRACED` / `PRE_DIRECTION_FWD` を要求し、socket cookie と cgroup ID が非 0 であることも確認する。
試験用 Pod 集合で、Service selector が当該 Pod 1 個を選択することを確認する。
Node からの別のヘルスチェックを代わりの証拠にはしない。

PRE は **Service の socket lookup の観測**であり、変換後 backend や TCP handshake 完了の直接証拠ではない。
通信の成功は curl の終了コードで別に確認する。`--flow-validation strict` を指定しても、
この項目は公式版の SYN / FIN の観測基準と同一にはならない。

`.3` の 6 秒待機は、検証環境の `monitor-aggregation=medium` / interval `5s` を前提とする。
稼働中の BPF 実装には socket event の出力間隔制限があり、新規接続でも event が抑制され得た。
待機により準備通信から間隔を空けるが、他の通信が先に出力枠を使う可能性は残る。
interval を動的に読み取って待機時間を変更する実装ではないため、別の設定へ流用するときは再評価する。
複数 backend の一般的な Service、socket trace がない環境、任意の負荷下での無欠落を保証する候補ではない。

## 3. 準備

必要なものは Bash、Git、`realpath` / `mktemp` / `sha256sum`、Go、公式 GitHub への通信である。
検証時は **Linux / amd64、Go 1.27.1、CGO 無効**を使用した。元の `go.mod` の指定は `go 1.26.0`。
以下は検証時と同じ Go 1.27.1 を `PATH` で選択済みであることを確認して進める。
`GOTOOLCHAIN=local` により、Go 自身による別 toolchain の自動取得は行わない。

この containerlab リポジトリのルートから、**同じ端末**で以下を順に実行する。
各ブロックがエラーで終了した場合は、原因を解消してから次へ進む。
ビルド出力と取得ソースは、Git 管理外の新しい一時ディレクトリへ保存する。

```bash
export PATCH_DIR="$(realpath nxos_fabric/docs/cilium-lab/cli-lab-flowfix)"
export BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cilium-cli-flowfix-XXXXXXXX")"
export SOURCE_DIR="${BUILD_ROOT}/source"

(
  set -euo pipefail
  : "${PATCH_DIR:?}" "${BUILD_ROOT:?}" "${SOURCE_DIR:?}"
  test -d "${PATCH_DIR}"
  test -d "${BUILD_ROOT}"
  export GOTOOLCHAIN=local
  command -v git
  command -v go
  go version
  test "$(go env GOVERSION)" = go1.27.1
  cd "${PATCH_DIR}"
  sha256sum -c SHA256SUMS
  printf 'source=%s\nbuild=%s\n' "${SOURCE_DIR}" "${BUILD_ROOT}"
)
```

`SHA256SUMS` の各項目が `OK`（環境によっては `完了`）なら、配布したパッチ類の内容は一致している。
これは同梱ファイルの整合性確認であり、第三者による署名検証ではない。

## 4. 公式ソースを取得し、版を確認する

タグ付きの公式ソースを新規取得する。`detached HEAD` の案内は、タグのコミットを直接参照しているためで正常。
記録したコミットと一致しなければ、パッチ適用へ進まない。

```bash
(
  set -euo pipefail
  : "${SOURCE_DIR:?}" "${PATCH_DIR:?}"
  git clone --depth 1 --branch v0.19.7 \
    https://github.com/cilium/cilium-cli.git "${SOURCE_DIR}"
  cd "${SOURCE_DIR}"
  test "$(git rev-parse HEAD)" = 7ca7fc53c20275f5c10ef5f3557076691fd1d720
  git rev-parse HEAD
  sha256sum -c "${PATCH_DIR}/UPSTREAM.SHA256SUMS"
)
```

## 5. 修正コードを確認・適用する

`git apply --stat` で変更対象を確認し、`--check` で適用可能か確認してから適用する。
最後のハッシュ一致で、生成された 10 ファイルが検証用 CLI のビルドに使った修正コードと一致することを確認する。

```bash
(
  set -euo pipefail
  : "${SOURCE_DIR:?}" "${PATCH_DIR:?}"
  cd "${SOURCE_DIR}"
  test "$(git rev-parse HEAD)" = 7ca7fc53c20275f5c10ef5f3557076691fd1d720
  test -z "$(git status --porcelain)"
  git apply --stat "${PATCH_DIR}/v0.19.7-lab-flowfix.3.patch"
  git apply --check "${PATCH_DIR}/v0.19.7-lab-flowfix.3.patch"
  git apply "${PATCH_DIR}/v0.19.7-lab-flowfix.3.patch"
  sha256sum -c "${PATCH_DIR}/PATCHED.SHA256SUMS"
  git status --short
)
```

新規ファイルには `??`、既存ファイルの修正には `M` が表示される。ブランチ作成や commit は不要。
パッチを適用済みのディレクトリでこのブロックを再実行すると、未変更確認で止まる。
やり直す場合は新しい `BUILD_ROOT` を作り、手順 3 から実施する。

## 6. 単体テストを実施する

誤った Pod / Service / IP / port / family、予期しない drop / RST を不合格にすることを確認する。
HTTP proxy を使う条件では、TCP の観測だけでは通らず HTTP event が必要であることも検証する。
`-mod=vendor` により、取得したソースに同梱される依存ライブラリを使う。

```bash
(
  set -euo pipefail
  : "${SOURCE_DIR:?}" "${BUILD_ROOT:?}"
  cd "${SOURCE_DIR}"
  export GOTOOLCHAIN=local CGO_ENABLED=0
  export GOCACHE="${BUILD_ROOT}/go-cache"
  packages=(
    ./vendor/github.com/cilium/cilium/cilium-cli/connectivity/check
    ./vendor/github.com/cilium/cilium/cilium-cli/connectivity/filters
    ./vendor/github.com/cilium/cilium/cilium-cli/connectivity/builder
    ./vendor/github.com/cilium/cilium/cilium-cli/connectivity/tests
  )
  go test -buildvcs=false -mod=vendor -p 4 -run TestLab -v \
    "${packages[@]}" 2>&1 | tee "${BUILD_ROOT}/unit-tests.log"
  go test -buildvcs=false -mod=vendor -p 4 \
    "${packages[@]}" 2>&1 | tee "${BUILD_ROOT}/package-tests.log"
)
```

`check` / `builder` が `ok` で、`FAIL` がなければ成功。
`filters` / `tests` の `[no test files]` は、そのパッケージに直接のテストファイルがない表示。
関連する照合ロジックは `check` 側のテストから呼び出している。

## 7. バイナリをビルドし、版とハッシュを記録する

`-X ...CLIVersion=...` は表示するバージョン名、`-o` は出力先を指定する。
`-buildvcs=false` はビルドへの VCS 情報埋め込みを無効にする。`-p 4` はビルドの並列数を制限する。

```bash
(
  set -euo pipefail
  : "${SOURCE_DIR:?}" "${BUILD_ROOT:?}" "${PATCH_DIR:?}"
  cd "${SOURCE_DIR}"
  export GOTOOLCHAIN=local CGO_ENABLED=0
  export GOCACHE="${BUILD_ROOT}/go-cache"
  test "$(go env GOVERSION)" = go1.27.1
  sha256sum -c "${PATCH_DIR}/PATCHED.SHA256SUMS"
  mkdir -p "${BUILD_ROOT}/bin"
  go build -buildvcs=false -mod=vendor -p 4 \
    -ldflags '-s -w -X github.com/cilium/cilium/cilium-cli/defaults.CLIVersion=v0.19.7-lab-flowfix.3' \
    -o "${BUILD_ROOT}/bin/cilium-lab-flowfix" ./cmd/cilium
  "${BUILD_ROOT}/bin/cilium-lab-flowfix" version --client | tee "${BUILD_ROOT}/version.log"
  go version -m "${BUILD_ROOT}/bin/cilium-lab-flowfix" > "${BUILD_ROOT}/build-info.log"
  cd "${BUILD_ROOT}"
  sha256sum bin/cilium-lab-flowfix unit-tests.log package-tests.log \
    version.log build-info.log > SHA256SUMS
  sha256sum -c SHA256SUMS
  printf 'binary=%s\n' "${BUILD_ROOT}/bin/cilium-lab-flowfix"
)
```

バージョン出力に `v0.19.7-lab-flowfix.3` が含まれれば、識別名の設定を確認できる。
`version --client` に表示される `cilium image (default)` は CLI の既定値であり、接続先クラスタの
Cilium Agent のバージョンを確認した表示ではない。
再ビルド時のバイナリハッシュは、ビルドパス・toolchain・対象 OS / architecture などで変わり得る。
`provenance.json` の値は元の検証バイナリの参考値であり、新しい出力に必ず同じ値を要求するものではない。
この手順ではソースの一致、テスト、出力バージョン、今回生成したハッシュを確認する。

## 8. 実機試験への受け渡し

別ホストで使用する場合は、対象の OS / architecture が対応していることを確認し、
`bin/cilium-lab-flowfix` と作成した証跡を専用ディレクトリへ転送する。転送後にもハッシュを照合する。
既存の標準 `cilium` と区別するため、実行時は生成したバイナリのパスを明示する。

このビルドの成功と実機の connectivity 試験の合格は別に確認する。
使用するクラスタの socket trace、aggregation interval、試験用 Service の構成を確認してから、
自己宛 Service / FQDN と関連する許可・拒否の限定試験を実施する。

2026-09-06 の元の候補では限定・回帰・自己宛の追加確認、計 114 actions が成功した。
長時間の全体試験や、別環境での同一結果まで保証する記録ではない。
今回の文書整備に際しても、固定した公式コミットからパッチ適用・テスト・ビルド・版表示を再確認済み。
元のビルド作業ツリーの Go コードを公式アーカイブ全体と比較し、差分が同梱の 10 ファイルに収まることも確認した。
実測値・コマンド原本・ログは `operations/cilium-lab/<日付>/<cluster>/` の結果報告に残し、
公開用の再現手順と分離する。実行サーバ固有のパスは
[実際の試験環境](execution-environment-singlesite-k02.md) を参照する。
