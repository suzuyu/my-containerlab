# 2026-09-13 の保存時点

## 検証の区切り

「single-site を既知課題付きで一区切りとし、multisite の k02／k03 基盤構築と
Cluster Mesh の双方向基本通信まで確認した状態」を保存する。
性能・障害系・全体 connectivity の合格は次の区切りとし、今回の成功へ含めない。

- single-site：最終構成、MTU／Egress 初期化、限定回帰を確認済み。
  全体 connectivity は 80/82 tests 成功の記録を維持する。
- multisite：k01 MetalLB の限定調査、k02／k03 の Cilium・LB／BGP・Mesh API・Hubble・Tetragon 導入を完了。
- Cluster Mesh：サイト間 Pod HTTP 16/16、Global Service HTTP 8/8、外部 k03 LB HTTP 12/12 成功。
- BDC Leaf MTU、Mesh の固定 VIP による名前解決、API の順次更新方式を修正し、保存設定へ反映済み。

詳しい条件と証跡は [k02 初回導入](k02-initial-install.md)、
[k03 導入と Mesh 接続](k03-clustermesh-install.md)、
[single-site 終了時確認](../../singlesite/2026-09-13/singlesite-closeout-2026-09-13.md) を参照する。

## 保存前の追加確認

2026-09-13 に clab02 で読み取り確認を実施した。

| 項目 | 結果 |
|---|---|
| k02／k03 Node | 各 3/3 Ready |
| Cilium／Tetragon | 各クラスタとも各 3/3 Ready |
| Mesh API | 各 2/2 Ready |
| Mesh 接続 | 双方向とも agent 3/3、KVStoreMesh 2/2 connected |
| BGP | 各クラスタ 8/8 Established |
| UI 用 demo | 両サイトの `cilium-test` に client／server Ready、Service affinity は `remote`。ブラウザでの表示確認は利用者側で行う |
| メモリ | MemAvailable 約 `11.0 GiB`、swap 使用 `0`。一時試験 Pod と UI 用 demo を含む時点 |
| Python テスト | `scripts/cilium-lab/tests` の 28 件成功。実クラスタへ変更を行わないテスト |
| Shell 構文 | 変更した 3 本で `bash -n` 成功 |
| 文書リンク | Cilium 文書 52 ファイルのローカルリンク先欠落 0。見出し anchor の完全検査ではない |
| 差分・公開 config | `git diff --check` 成功。122 config のサニタイズ検査成功、username 除去対象 0、許容する lab 向け管理設定 530 件を保持 |
| Go テスト | `egress-latency-probe` は実行ホストの PATH に Go がなく、今回は再実行していない |

追加の実測は状態確認に限定し、性能・障害試験やブラウザ操作を再実行したわけではない。
読み取り結果は Git 管理外の `nxos_fabric/nxos_multisite/operations/cilium-lab/2026-09-13/checkpoint/` に保持する。

## 一時リソースの扱い

ユーザーの承認を得て、両クラスタの自動試験用 namespace `cilium-mesh-bootstrap-check` を撤去した。
namespace の消滅と、UI 用 demo の Pod／Service が残っていることを確認した。
撤去後も両サイトで BGP 8/8 Established、Mesh agent 3/3・KVStoreMesh 2/2 connected を維持した。
中断した DNS 試験 Pod `coredns-upstream-direct-2803307` は追加確認時には存在しなかった。

ブラウザ用の `cilium-test` は再利用する demo として保持した。
通信ループの停止と `remote`／`local` の切替は
[multisite README のデモ手順](../../../../../nxos_multisite/README.md#hubble-ui-access) に従う。

## 次の区切りに回す作業

| 優先度 | 作業 | 今回の保存への影響 |
|---|---|---|
| 次の受入で優先 | Mesh API 片系停止・復旧、経路退避、Global Service の local 優先／remote fallback | 基本構築とは別の障害・冗長性試験として開始する |
| 次の受入で優先 | multisite の MTU 境界、性能・資源測定 | 小さい HTTP の成功と分けて受入する |
| 新規構築の再現性確認で必要 | kubelet Node IP の未反映と初回 ARP／ND 解決の原因調査 | 手動補正を含む実績として保存し、無介入で再現可能とはしない |
| 継続調査 | single-site の TI-004、全体 connectivity の未合格分 | 既知課題を残した記録として保存できる |
| 後続操作で一部完了 | Leaf の `write memory` | clab02 の BDC Leaf0101／0102 は後続の明示依頼で保存済み。single-site（clab01）は別途未実施 |
| 保留 | kernel 更新、Node 再起動、WireGuard／Egress と Mesh の発展試験 | 合意済みの順序に従い、今回の保存条件にはしない |

## Git 保存の範囲

`nxos_fabric/` 配下の文書整理、single-site の設定・試験記録、multisite の CDC 除外構成・
設定・手順・結果、および関連する script／test を一緒に保存する。
移動元の削除と移動先の新規ファイルは同じ commit に含める。

runtime、kubeconfig、秘密情報、生ログ、capture、`operations/`、`clab-*` は Git 保存対象外。
別変更の `.gitignore` と `nxos_spine-leaf/README.md` は作業ツリーに保持する。
ローカル commit とリモートへの push は別操作として扱う。

## 後続の push と機器への保存

ユーザーの明示依頼により、保存 commit `90caacc` を `origin/evpn-multisite` へ push した。
同日、clab02 の BDC Leaf0101／0102 で `copy running-config startup-config` を実行し、
両機の `Copy complete` と、startup-config の Po14〜16 にある `mtu 9216` を確認した。
single-site（clab01）の保存操作はこの後続作業の対象に含めていない。
