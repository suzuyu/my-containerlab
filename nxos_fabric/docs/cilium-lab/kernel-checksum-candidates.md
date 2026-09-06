# IPv6 checksum 恒久対応候補の評価（2026-09-06）

## 1. 結論

**当面は検証済みの互換設定と条件付き再適用監視を維持する。**
今回取得した Rocky Linux `5.14.0-687.44.1.el9_8` は、ソース上も `BPF_F_IPV6` を受け付けないため、今回の障害を解消する更新先としては採用しない。
この判断は当該 checksum 障害の修正可否についてであり、OS の通常保守更新の価値を否定するものではない。

kernel／OS 更新やホスト再起動は実施していない。修正済みの実行環境で、回避策なしの実通信が成功したという結論でもない。

## 2. 確認した候補と根拠

| 対象 | 確認結果 | 採用判断 |
|---|---|---|
| 稼働中 Rocky Linux 9.7、`5.14.0-611.27.1.el9_7.x86_64` | helper 実測で対照 flags 0／16 は成功、144 は `-EINVAL` | 現状は回避策付きで運用 |
| リポジトリ候補 `5.14.0-687.44.1.el9_8` | 公式 source RPM の署名・digest が OK。helper の許可マスクに IPv6 フラグなし | 該当修正の候補から除外。導入・起動による実測は未実施 |
| Linux 上流修正 `ead7f9b8de65632ef8060b84b0c55049a33cfea1` | IPv6 用フラグを導入する修正が存在 | OS ベンダー側に取り込まれた候補を調べる際の照合対象 |
| 取得時の Cilium `main` の `ipv6_l4_csum_update()` | 新フラグを試し、`-EINVAL` 時は従来分岐へ戻る構造を維持 | 取得した関数だけでは旧 kernel 向けの今回の恒久修正を確認できない |

Rocky Linux の候補は実行サーバの `dnf --cacheonly list --showduplicates kernel-core` と `repoquery` から選んだ。
全ディストリビューション・全 kernel を網羅した調査ではない。

[Rocky Linux 公式 source RPM](https://dl.rockylinux.org/pub/rocky/9.8/BaseOS/source/tree/Packages/k/kernel-5.14.0-687.44.1.el9_8.src.rpm) の
`net/core/filter.c` では、`BPF_F_MARK_MANGLED_0`、`BPF_F_MARK_ENFORCE`、`BPF_F_PSEUDO_HDR` とフィールドサイズ以外のビットを `-EINVAL` で拒否する。
`include/uapi/linux/bpf.h` にも `BPF_F_IPV6` の定義はない。
ソースの確認は未対応の根拠となるが、新しい kernel を起動して副作用まで確認した試験ではない。

上流の修正は [Linux 5.10.239 の公式 ChangeLog](https://cdn.kernel.org/pub/linux/kernel/v5.x/ChangeLog-5.10.239) にも backport として記録されている。
関連する `inet_proto_csum_replace_by_diff()` の修正 `6043b794c7668c19dabc4a93c75b924a19474d59` と合わせて確認する。
これは、単に `5.14` が `5.10` より新しいから対応している、とは判断できない具体例である。
古い `5.10.239` を今から導入することを推奨するものではない。

[Cilium 上流の該当処理](https://github.com/cilium/cilium/blob/main/bpf/lib/lb.h) の確認結果は取得時点のもの。
全 PR を調べて「修正が存在しない」と断定した結果ではない。旧 helper 時に ingress／egress と checksum 状態を正しく扱う変更があるかを、採用する release／commit ごとに再確認する。

## 3. 恒久対処の進め方

1. **OS ベンダーの対応候補を選ぶ。** 上記 2 修正または同等処理を含む package を特定する。単なる最新 package の選択では不十分。
2. **隔離した環境で候補 kernel を起動する。** 稼働中ホストと同じ Cilium image／VXLAN／dual-stack／LB SNAT 条件に揃え、helper を実測する。
3. **回避策なしで受入を行う。** 両方向の Node 間 IPv6 LB と受信 checksum、Service／NodePort、Egress、Policy／Tetragon、CPU／メモリと TCP／UDP 負荷を確認する。
4. **現行ホストへの適用を別の変更枠にする。** 全 containerlab／kind への影響、旧 kernel へ戻す起動方法、証跡、監視の停止・再登録を準備する。
5. **回避策を解除する。** 監視を停止して元の feature を復元し、通信と再起動後の状態が正常なことを確認してから例外を廃止する。

現行 OS 系列で適合候補が得られない場合は、対応済み kernel を含む別 OS 系列の検証か、Cilium の公式修正候補を比較する。
今回の稼働ホストへ mainline kernel や独自 BPF パッチを直接導入しない。
IPv6 無効化、DSR、`externalTrafficPolicy: Local` への切替も、自動的な代替策にはしない。

## 4. 相談・修正評価に使える事実

- 現行 Cilium は `1.20.1 / 7d68cfb3`。kind Node はホスト kernel を共有する。
- IPv6 Cluster VIP は同一 Node の backend で成功し、Node 間転送で受信 TCP checksum 不正が再現した。
- 両 worker の `cilium_vxlan` で `tx-checksum-ip-generic off` にすると改善し、on に戻すと再現した。
- helper 単体試験は通信に attach しておらず、対照フラグ成功・IPv6 フラグ `-22` を分離して確認した。
- 回避策で TSO も off になり、小さい HTTP の短時間比較では平均処理率が約 11.4% 低下した。offload 単独の最大性能への影響は未確定。
- 稼働 packet の `skb->ip_summed` を直接追跡した確定診断や、修正コードの実証は未実施。

これらを添えて修正候補を評価する。外部への問い合わせ・Issue 投稿は今回行っていない。

## 5. 関連資料

- [登録・再適用・監視・解除手順](checksum-compat-operations.md)
- [kernel 判定と設計方針](kernel-compatibility-policy.md)
- [導入・検証結果と候補ソース証跡](../../nxos_singlesite/operations/cilium-lab/2026-09-06/adc-k02/checksum-monitor-result.md)
