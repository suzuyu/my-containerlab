# VXLAN checksum 互換設定の登録・再適用・監視

## 1. 目的と適用範囲

検証済みの kernel／Cilium／VXLAN 構成で、Node や interface の再作成により TX checksum 設定が戻った場合に、条件を照合して再適用する。
これは IPv6 LB 障害に対する暫定運用であり、kernel の恒久修正ではない。
判断基準は [kernel 対応方針](kernel-compatibility-policy.md)、実際の対象・証跡は [single-site 実行環境](execution-environment-singlesite-k02.md) を参照する。

### 1.1 `tx-checksum-ip-generic = off` は何を意味するか

checksum は、通信データの破損を検出するための値である。今回の設定は、checksum を計算する処理方法を変更する。

| 項目 | 意味 |
|---|---|
| `cilium_vxlan` | Cilium が Node 間通信に使う VXLAN の仮想 interface |
| `tx-checksum-ip-generic` | TCP／UDP などの送信 checksum 計算を、後段のデバイス処理へ任せる機能 |
| `off` | この interface ではその機能を使わず、必要な計算をソフトウェア側で完了させる |

**off は checksum の計算や検査を省略する意味ではない。**
仮想 interface の offload は、必ず物理 NIC だけで計算するという意味でもない。
Linux は送信先 interface で利用できる機能に応じて、必要な checksum 処理をソフトウェアで補う。
[Linux 公式の checksum offload 説明](https://docs.kernel.org/networking/checksum-offloads.html) を参照する。

### 1.2 今回の kernel の制約との関係

1. Cilium は IPv6 の NAT でアドレスを書き換える際、TCP／UDP の checksum も更新する。
2. 現行 kernel では、その更新に使う helper `bpf_l4_csum_replace` の追加フラグ `BPF_F_IPV6` が未対応だった。
3. 今回の環境では、Node 間 IPv6 LB と checksum offload の組合せで、外部受信時の TCP checksum 不正が再現した。
4. 両 worker の VXLAN TX checksum offload を無効にすると、試験した通信では不正が発生しなくなった。on に戻すと再現した。

したがって、この設定は **現在の kernel を使い続けながら、問題が出る処理の組合せを避ける回避策**である。
kernel を更新したり、未対応フラグを利用可能にしたりする設定ではない。
旧 helper 向けの処理と offload の相互作用が最有力だが、稼働 packet の内部状態を直接追跡した確定診断や、恒久修正コードの検証までは行っていない。

関連する TSO も off になり、前回の短時間負荷では平均処理率が約 11.4% 低かった。
offload 単独の影響と断定できる測定ではないが、性能影響なしとは扱わない。
具体的な結果は [回避策適用後の回帰試験](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/offload-regression-result.md) に記録している。

### 1.3 Cilium Pod 再作成試験で何を確認するか

Cilium は既存の DaemonSet／ConfigMap／Policy 等に従って起動し、状態を再同期する。
今回導入した監視は、Cilium が Ready になった後に登録条件と interface の状態を照合し、必要な場合だけ `tx-checksum-ip-generic off` を再適用する。
**既に off が維持されていれば、確認だけで設定変更はしない。** Pod 再作成で必ず設定が失われるという前提ではない。

試験目的は、Pod が入れ替わっても監視が継続し、回避策と IPv6 LB 通信が正常であることの確認である。
新しい Cilium version や設定を投入するための再作成ではない。
今回の実施範囲からは kernel 変更、kind worker と実行ホストの再起動を除外する。

2026-09-06 に両 worker の Cilium Pod を 1 台ずつ再作成し、[動作試験を完了した](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/checksum-pod-restart-result.md)。
両 Pod とも約 17 秒で Ready となり、既存の VXLAN interface と off 設定が維持された。監視は新しい Pod UID を認識し、設定の再書き込みは不要だった。
再作成中の HTTP 208 件と復旧後の HTTP 84 件は成功し、Node 間 IPv6 LB の両方向と受信 checksum も確認した。
この結果は Pod 再作成時の維持確認である。設定が on に戻った場合の timer による自動修復は、[前回の設定ずれ注入試験](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/checksum-monitor-result.md) で別に確認している。

### 1.4 使用するツール

| ツール | 役割 |
|---|---|
| `probe-ipv6-checksum.py` | 未 attach の合成 packet で helper フラグを実測する。interface を変更しない |
| `probe-ipv6-checksum.go` | Python のない Linux/amd64 kind Node 用の静的プローブ |
| `checksum-compat.py enroll` | 対象 cluster／Node、kernel、image、通信設定と復元値を明示登録する。NIC を変更しない |
| `checksum-compat.py check` | 登録条件と現在値を照合する。変更なし、ずれや判定不能は非 0 終了 |
| `checksum-compat.py reconcile` | 条件一致時に限り off を再適用する。設定済みなら書き込まない |
| `checksum-compat.py restore` | 登録した元の値へ戻し、成功時に登録を無効化する |
| `install-checksum-monitor.py` | 登録した 1 環境を監視する user systemd service／timer を作成する |

全ファイルは `nxos_fabric/scripts/cilium-lab/` にある。スクリプトや unit を変更したら、ローカル検査と実行サーバへの転送を行う。Git 同期を前提にしない。

## 2. Cilium 導入前の helper 判定

ホストの基本 preflight に加え、BPF program load／test run の権限がある環境で実行する。

```bash
python3 "${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/probe-ipv6-checksum.py"
echo "probe_exit=$?"
```

| 出力 `status` | 終了コード | 意味 |
|---|---:|---|
| `supported` | 0 | 対照フラグと IPv6 フラグが利用可能。実通信の合格は別途必要 |
| `unsupported` | 3 | 対照は成功し、IPv6 フラグだけ `-EINVAL`。検証済み互換設定か修正候補を選ぶ |
| `unknown` | 2 | 権限不足、load／test run 失敗、未対応 architecture 等。未対応と断定しない |

一般ユーザーの実行が `unknown`／`errno=1` なら、BPF 権限のある実行場所で測り直す。
この Python 実装は Linux little-endian の x86_64／aarch64 の syscall 番号を扱う。
今回、helper の正常実行は Go 版の x86_64 で確認した。Python 版は権限不足の経路と分類ロジックを確認しており、権限を与えた環境での helper 実行と aarch64 の実機確認は未実施。
合成 packet の zero-diff 試験であり、実際の reverse NAT や skb の全状態を検証するものではない。

Python のない kind Node では Go 版を使う。導入前に用いる場合も、同じホスト kernel を使う隔離した検証環境で実行し、kernel を照合する。

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
  -o /tmp/probe-ipv6-checksum \
  "${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/probe-ipv6-checksum.go"

# NODE は今回確認する kind Node。別ホストの結果を流用しない。
(
  : "${NODE:?対象 kind Node を設定してください}"
  probe_path=$(docker exec "${NODE}" mktemp /usr/local/bin/checksum-probe-XXXXXXXX) || exit 1
  trap 'docker exec "${NODE}" rm -f "${probe_path}"' EXIT
  docker exec -i "${NODE}" sh -c 'cat > "$1" && chmod 700 "$1"' sh "${probe_path}" \
    < /tmp/probe-ipv6-checksum || exit 1
  docker exec "${NODE}" uname -r
  docker exec "${NODE}" "${probe_path}"
)
```

Go 版は測定成功時に 0 終了する。**helper 対応の合否は各行の値で判定する**。Python 版の終了コード 3 と混同しない。

```text
flags=0 test_syscall_errno=0 helper_return=0
flags=16 test_syscall_errno=0 helper_return=0
flags=144 test_syscall_errno=0 helper_return=-22
```

上記は今回の実測で、対照成功・IPv6 フラグ未対応を表す。load／test run の失敗や行不足は判定不能とする。

## 3. 導入後の明示登録

Cilium と対象 worker が Ready、`cilium_vxlan` が存在する段階で登録する。
登録は kernel や image を「安全と証明する」操作ではなく、別途合格した範囲を固定する操作である。
同じ state ファイルへの上書き登録は拒否する。更新後は古い証跡を保持し、新しいパスへ再登録する。

```bash
: "${REPO_ROOT:?}" "${KUBECONFIG:?}"
export COMPAT_SCRIPT="${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/checksum-compat.py"
export COMPAT_STATE="${REPO_ROOT}/nxos_fabric/nxos_singlesite/operations/cilium-lab/runtime/adc-k02/checksum-compat.json"

python3 "${COMPAT_SCRIPT}" enroll --state "${COMPAT_STATE}" \
  --cluster adc-k02 --context kind-adc-k02 --kubeconfig "${KUBECONFIG}" \
  --node adc-k02-worker --node adc-k02-worker2 \
  --restore-tx on \
  --reason 'helper 未対応と checksum 回避策の実通信試験に合格。対応する証跡 ID をここに記入する'

python3 "${COMPAT_SCRIPT}" reconcile --state "${COMPAT_STATE}"
python3 "${COMPAT_SCRIPT}" check --state "${COMPAT_STATE}"
```

`--restore-tx on` は変更前の記録が on の場合だけ指定する。既に off の環境で変更前が不明な場合は、元の値を推測しない。
元の値が Node ごとに異なる場合は、別 state へ分ける。

対象名、kind の cluster／worker label、Node Ready、Cilium Ready、VXLAN interface の種類を確認する。
登録後は cluster UID、ホスト kernel、Node image ID、Cilium image ID と通信に関係する ConfigMap の値が一致しない限り、変更しない。
同じ image／kernel の Node container や Cilium Pod の再作成は許容する。新しい interface を確認し、正しい container ID と ifindex に対して適用する。
cluster 全体の再作成で UID が変わった場合は再登録が必要である。

成功時の出力例:

```json
{"action":"reconcile","status":"ok","changed":[]}
```

`changed: []` は検査済みで変更不要、Node 名が入る場合はその Node を off に再設定したことを表す。
全 offload 項目、ifindex、image、時刻は state と同じ場所の `checksum-compat.status.json` に保存する。
失敗時は `status: blocked`、理由、非 0 終了となる。**単に state ファイルがあることや古い成功結果だけで合格にしない。**

## 4. 30 秒間隔の監視

```bash
export RUNTIME_BIN="${REPO_ROOT}/nxos_fabric/nxos_singlesite/k8s_kind/client/runtime/bin"
export PATH="${RUNTIME_BIN}:${PATH}"

# user manager をログアウト後・ホスト起動後にも動作させる。ユーザー全体に影響する設定。
loginctl enable-linger "$(id -un)"

python3 "${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/install-checksum-monitor.py" \
  --state "${COMPAT_STATE}" --runtime-bin "${RUNTIME_BIN}" \
  --unit cilium-checksum-adc-k02

systemctl --user status cilium-checksum-adc-k02.timer --no-pager
systemctl --user show cilium-checksum-adc-k02.service \
  -p Result -p ExecMainStatus -p ExecMainStartTimestamp
journalctl --user -u cilium-checksum-adc-k02.service -n 20 --no-pager
python3 "${COMPAT_SCRIPT}" check --state "${COMPAT_STATE}"
```

timer が active でも直近 service が失敗している場合は合格ではない。`Result=success`、`ExecMainStatus=0`、直近時刻、check の成功を確認する。
API／Docker に接続できない、Node が停止中、image/kernel が変わった場合は journal と status ファイルへ失敗を出し、次周期も再確認する。
Slack／メール等への外部通知は実装していない。

30 秒は厳密な復旧 SLA ではない。検査時間や起動準備時間が加わる。
**interface が作られてから再適用するまでの間、通信を物理的に遮断する機構はない。**
既存 BGP 広報や Service も自動撤回しない。計画更新では利用開始前に明示的な `reconcile`／`check` と LB 実通信を行う。

## 5. 構築・変更手順への組込み

既存 single-site の収束スクリプトには明示オプションを追加した。

```bash
# これは既存の Helm upgrade 等も実行する構築コマンド。監視の確認だけなら実行しない。
"${REPO_ROOT}/nxos_fabric/scripts/cilium-lab/converge-cilium-lab.sh" \
  --profile singlesite-final --context-k02 kind-adc-k02 \
  --checksum-state-k02 "${COMPAT_STATE}" --apply
```

Cilium Ready 後、platform CR 適用前に互換設定を再適用・確認する。失敗したら後続へ進まない。
既存の LB が稼働中の upgrade では、これだけで通信停止や広告撤回を保証しない。
Cilium image 更新時は登録条件が変わって止まるため、別途評価・再登録を行う。
初回は Cilium 導入後に手順 3 で登録する。このオプションだけで初回登録や kernel に応じた profile の自動選択は行わない。
今回、スクリプトへの組込みは検査済みだが、Helm upgrade 自体は再実行していない。

## 6. 停止・解除・恒久修正後の復元

監視を止めても interface 設定は維持される。性能比較等で on/off を変更する前にも timer を止める。

```bash
systemctl --user disable --now cilium-checksum-adc-k02.timer
systemctl --user stop cilium-checksum-adc-k02.service
```

恒久修正の評価で、登録した元の値へ戻す場合:

```bash
python3 "${COMPAT_SCRIPT}" restore --state "${COMPAT_STATE}"
```

成功時に state は disabled となり、reconcile による再適用を拒否する。
kernel／image を更新済みで fingerprint が違う場合は restore も止める。新環境の設定を確認し、変更対象を明示して復元する。
`tx-checksum-ip-generic` の元の値を復元する機能であり、全 feature を一括復元する機能ではない。関連する TSO 等の実状態も再読する。

unit を不要にした場合は、生成された以下の 2 ファイルを確認してから削除し、`systemctl --user daemon-reload` を実行する。

- `~/.config/systemd/user/cilium-checksum-adc-k02.service`
- `~/.config/systemd/user/cilium-checksum-adc-k02.timer`

linger は同じユーザーの他の service にも影響するため、監視を止めたことだけを理由に自動で解除しない。
今回の導入前は `Linger=no`。他の用途がないことを確認して元へ戻す場合は `loginctl disable-linger "$(id -un)"` を使う。
