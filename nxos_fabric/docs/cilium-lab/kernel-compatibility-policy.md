# Cilium 導入前の kernel 判定と IPv6 checksum 対応方針

## 1. 採用方針

**kernel の版番号だけで通信機能を合格にせず、helper の対応確認と、採用する経路の実通信試験を追加する。**
この文書は個人 lab の導入・変更判断を扱う。Cilium 全体の要件と、今回の IPv6 LoadBalancer に必要な条件を分ける。

現在の single-site k02 では VXLAN、dual-stack、LB SNAT、`externalTrafficPolicy: Cluster` を維持する。
当面は検証済みの VXLAN TX checksum 回避策を明示的に選択し、恒久対処は kernel または Cilium の対応修正を別変更として評価する。
未知の kernel に回避策を一律適用したり、IPv6 を黙って無効化したりしない。

`cilium_vxlan` の `tx-checksum-ip-generic off` の意味、checksum を省略しないこと、kernel の制約との関係と Pod 再作成試験の目的は、
[運用手順の 1.1～1.3 節](checksum-compat-operations.md#11-tx-checksum-ip-generic--off-は何を意味するか) にまとめる。

回避策適用後の限定回帰は Service／NodePort 等の 114 actions、Egress の 46 HTTP、LB の 42 HTTP が成功した。
一方、短時間 HTTP 負荷では off 側の平均処理率が約 11.4% 低く、性能影響なしとは扱わない。
順序・背景負荷を分離した測定と、大きい TCP／UDP の比較を恒久運用前に追加する。

実行環境・今回の結果は [single-site の回帰結果](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/offload-regression-result.md)、
原因を絞った比較は [offload 比較試験](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/lb-ipv6-offload-result.md) を参照する。

## 2. なぜ版番号だけでは不十分か

Cilium の基本要件には kernel 5.10 以降やディストリビューションの同等実装が含まれるが、個々の拡張機能には別の条件がある。
ディストリビューションによる backport もあるため、`uname -r` の大小だけでは特定 helper のフラグ対応を決められない。
[公式システム要件](https://docs.cilium.io/en/stable/operations/system_requirements/) を、使用する Cilium の版に合わせて確認する。

今回の環境では、基本要件を満たす kernel に対しても、`bpf_l4_csum_replace` の `BPF_F_IPV6` は `-EINVAL` だった。
稼働 Cilium の `ipv6_l4_csum_update()` には旧 helper 向けの分岐があり、Node 間 IPv6 reverse NAT と checksum offload の組合せで失敗が再現した。
これは全ての IPv6、全ての Cilium 機能、全ての kernel 5.14 が動作しないという意味ではない。

kind は Node をコンテナとして動作させる。今回の kernel 対応で確認・更新する対象は実行ホストであり、kind Node image や Cilium image の変更だけでホスト kernel は更新されない。
[公式 kind 概要](https://kind.sigs.k8s.io/) と、実行ホスト・Node 内の `uname -r` を照合する。

## 3. 導入前と導入後の判定順

| 時点 | 確認する内容 | 次へ進める条件 |
|---|---|---|
| Cilium 導入前 | 実行ホストの OS、kernel package と起動中 kernel、architecture、BPF/BTF、cgroup、使用予定の Cilium image digest | 対象版の基本要件と lab のリソース要件を満たす |
| Cilium 導入前 | IPv4/IPv6、VXLAN/native、LB SNAT/DSR、Cluster/Local、Egress Gateway の必要性 | 必要機能を明示した profile が確定している |
| Cilium 導入前 | 実行 kernel の helper フラグを単体プローブで確認 | `supported` / `unsupported` / `unknown` を記録し、下表の選択を行う |
| Cilium Ready 後 | `cilium_vxlan` の存在・ifindex・実際の offload 設定 | 互換 profile なら回避策を適用し、設定を再読して一致する |
| LB / Egress の利用開始前 | 同一 Node と別 Node の IPv6 LB、checksum、Service/NodePort、通常 Pod 間、Egress の実通信 | 選択した profile の期待値に合格する |
| Node / Cilium / kernel の更新後 | image・kernel・interface の再照合、必要時の再適用、回帰試験 | 更新後の状態を新しい証跡で合格にする |

`cilium_vxlan` は Cilium が作成するため、**導入前に方針を決め、導入後に interface 設定を適用する**。
導入前に interface がないことをエラー扱いしない。一方、適用すべき導入後の段階で見つからない場合は設定完了とみなさない。

### helper プローブの判定

今回の単体プローブは合成 IPv6/TCP パケットを使い、通信に attach しない BPF program で helper の戻り値を調べた。

| 結果 | 分類 | 扱い |
|---|---|---|
| 対照フラグと `BPF_F_PSEUDO_HDR \| BPF_F_IPV6` がともに成功 | supported | 新しいフラグは利用可能。実通信の合格を別途確認する |
| 対照フラグは成功、IPv6 フラグだけ `-EINVAL` | unsupported | 該当 profile の更新または互換策を選択する |
| 権限不足、program load / test run 失敗、対照も失敗、ツールなし、未対応 architecture | unknown | 未対応と決めつけない。原因を直して測定し直す |

今回の値は、対照 `flags=0` / `16` が `0`、`flags=144` が `-22`。プローブの正常実行と helper の戻り値を分けて扱う。
これはフラグの利用可否を測るもので、実際の reverse NAT の正しさや全ての checksum 状態の正常性を保証する試験ではない。

`bpftool feature probe` の一般的な helper 一覧や、コンテナ内ヘッダーに定数があることだけでは、実行 kernel が個別フラグを受け付ける証拠にならない。
プローブを `scripts/cilium-lab/probe-ipv6-checksum.py` と静的バイナリ用の Go ソースへ整理した。
[実行手順](checksum-compat-operations.md#2-cilium-導入前の-helper-判定) に従い、Python 版と Go 版の終了コードの違いにも注意する。
Go 版は Linux/amd64 専用。Python 版は aarch64 の syscall 番号も扱うが、今回の実機確認は x86_64 のみ。

## 4. 判定に応じた実装・設定の選択

| 条件 | 推奨する選択 | 自動で変更しない項目 |
|---|---|---|
| helper 対応、採用 profile の実通信も正常 | 通常 profile。不要な offload 無効化はしない | kernel / Cilium / LB mode |
| helper 未対応で、今回と同じ IPv6 VXLAN + LB SNAT の障害を確認 | 当面は明示した互換 profile。該当 Node の VXLAN TX checksum を無効化し、回帰・負荷を確認 | IPv6 の無効化、Service の Cluster→Local |
| helper 未対応で、現在の通信方式を維持した恒久対応が必要 | OS ベンダーの修正 kernel または対応済み Cilium の候補を別環境で検証 | kernel 更新・再起動、Agent/BPF の差替え |
| 通信方式を再設計できる | native routing、DSR/Hybrid、Local の採否を個別設計として比較 | ルーティング、送信元 IP、到達可能 Node の意味を変える自動 fallback |
| helper 対応でも checksum 障害がある | 別の原因として調査。対応フラグだけで合格にしない | 未検証の互換 profile |
| 判定不能 | 該当 profile の公開・受入を保留し、測定条件を整える | IPv4-only などへの暗黙切替 |

「互換 profile」はこの lab の運用方針の呼称であり、Cilium の既存 Helm value 名ではない。
TX checksum の変更は Linux interface の設定であり、架空の Helm option を追加して解決するものではない。

DSR/Hybrid や `externalTrafficPolicy: Local` は送信元保持や転送先の選択に関わる。今回の修正の代用として採用せず、BGP 広報、backend 配置、障害時の到達性まで再評価する。
[公式 kube-proxy replacement の説明](https://docs.cilium.io/en/stable/network/kubernetes/kubeproxy-free/) を参照する。

## 5. 暫定回避策の管理と永続化

回避策は対象 Node の network namespace 内で実行する。

```bash
# NODE は対象を事前に確認して指定する。
docker exec "${NODE}" ethtool -k cilium_vxlan
# 変更前の全出力を保存した後に実行する。
docker exec "${NODE}" ethtool -K cilium_vxlan tx-checksum-ip-generic off
docker exec "${NODE}" ethtool -k cilium_vxlan
```

現在の k02 は worker 2 台が対象。将来 backend を置く Node を増やす場合は対象を再評価する。
ホストの同名 NIC、管理 NIC、Fabric NIC の checksum 設定へ一括適用しない。

- この変更は VXLAN 送信全体に影響する。IPv6 LB の特定 VIP だけには限定されない。
- 関連する segmentation offload の有効状態も変わる。今回も両 Node の TSO が off になったため、変更前後の `ethtool -k` 全体を保存し、性能を比較する。
- Node 再作成、interface 再作成、Cilium 更新後に保持される前提にしない。
- 再起動に耐える暫定運用を作る場合は、Cilium Ready と対象 interface の生成後に実行する冪等な hook と、適用状態の監視を設ける。
- hook には対象 cluster/Node の限定、存在確認、設定再読、失敗時の公開保留、変更前への復元、適用時刻と image/kernel の記録を含める。
- `ethtool` の常時強制ループだけを先に導入しない。kernel 更新後には回避策が不要になったかを試験し、設定の解除条件を持たせる。

2026-09-06 に、明示登録した kernel／image／cluster に限定する再適用スクリプトと user systemd timer を実装し、single-site k02 へ導入した。
構築スクリプトにも Cilium Ready 後の明示的な再適用・確認オプションを追加した。
[登録・監視・解除手順](checksum-compat-operations.md) に従う。timer は 30 秒周期であり、interface 再作成直後の通信を自動遮断する機能ではない。
Node／ホストを実際に再起動した耐久確認は未実施。停止・再作成後は LB 実通信の受入を省略しない。

2026-09-06 の [Cilium Pod 再作成試験](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/checksum-pod-restart-result.md) は完了した。
両 worker で off 設定が維持され、監視は新しい Pod を認識し、再作成中と復旧後の LB 通信は成功した。
今回は interface 自体が維持されたため、再作成に伴う設定消失からの自動修復を実測した結果ではない。

## 6. 恒久対処の優先順位と合格条件

### 優先 1: OS ベンダーの修正 kernel を評価する

稼働中 OS で保守される修正候補を選び、helper probe、回避策なしの Node 間 IPv6 LB、Service/NodePort、Egress、Policy、観測・リソースを再確認する。
候補調査では、Rocky Linux `5.14.0-687.44.1.el9_8` の署名確認済み source RPM にも該当フラグの受入がなかった。
この package を今回の障害の修正済み候補とは扱わない。[恒久候補の調査結果](kernel-checksum-candidates.md) を参照する。
特定の mainline 版番号以上なら十分とはしない。ディストリビューションの package と実行 kernel を照合する。
実行ホストの再起動は containerlab / kind 全体へ影響するため、復旧手順と実施枠を別に設ける。

### 優先 2: Cilium の対応修正を評価する

公式修正で今回の旧 helper / ingress checksum offload の条件を扱っていることをソース・テストで確認する。
今回の候補を根拠に `BPF_F_PSEUDO_HDR` を無条件追加する独自パッチを直接適用しない。`CHECKSUM_COMPLETE` など別状態への影響もあるためである。
kernel 更新が難しい場合に、対応済みリリースまたは検証用修正を別環境で評価する。

### 恒久対応後に回避策を解除する条件

1. helper / 実装の対応を記録し、対象 image/kernel を固定する。
2. offload を通常値に戻し、入口と backend の組合せを明示した IPv6 LB が両方向で成功する。
3. 外部受信 checksum、通信エラー、関連 drop の期待値を満たす。
4. Service/NodePort、Pod 間、Egress の回帰に合格する。
5. 大きい TCP payload、UDP、並列数を変えた負荷と CPU/メモリを比較する。短時間の小さい HTTP だけで最大性能を判定しない。
6. Node / Cilium 再起動後も再発しないことを確認し、互換 hook と例外記録を解除する。

## 7. 既存 preflight への組込み範囲

`preflight-host-and-kind.sh` の基本・リソース検査は維持する。その `FAIL=0` は今回の helper / IPv6 LB 経路の合格を意味しない。
追加の helper 判定ツール、明示登録・再適用・監視と構築時の確認オプションは実装済みである。
基本 preflight からの helper 自動実行や、未検証環境の profile 自動選択は実装していない。

- 導入前: OS/kernel/image と必要機能を入力にした capability 判定を保存する。
- 判定出力: supported / unsupported / unknown、採用 profile、判定根拠、再確認条件を分ける。
- 導入後: interface 作成を待って選択した互換設定を適用し、実状態を検査する。
- 公開前: Node 間 IPv6 LB の受入を追加し、失敗を単なる warning にしない。
- 更新後: kernel・Cilium・Node image・interface の変更を契機に判定と受入をやり直す。

実行コマンドと具体的な出力の見方は [互換設定の運用手順](checksum-compat-operations.md) を参照する。

## 8. 参照

- [Linux: Checksum Offloads](https://docs.kernel.org/networking/checksum-offloads.html)
- [Cilium: IPv6 checksum 更新処理](https://github.com/cilium/cilium/blob/main/bpf/lib/lb.h)
- [リソースと既存 preflight](resource-and-preflight.md)
- [構築計画 Stage 1 / Stage 2](build-plan.md)
