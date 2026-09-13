# clab02：multisite 起動前の構成・イメージ検討

2026-09-13 の事前評価。実行先は clab02 で、containerlab は未起動。
**比較用 k01 を残す要望に合わせ、CDC のみを除外した 2 サイト構成を作成した。**
[CDC 除外版 YAML](../../../nxos_multisite/nxos-fabric-multisite-no-cdc.clab.yaml) は、ユーザーが clab02 に追加した
`vrnetlab/cisco_n9kv:10.6.4.M.lite` を指定する。代表構成での動作確認は未実施。
3 サイト版と CDC 除外版の NX-OS 指定を `10.6.4.M.lite` に統一した。lab の起動・停止・設定投入は実施していない。

## 1. 実行環境と資源

ホスト、Docker の稼働一覧・イメージ一覧、保存 topology を読み取り確認した。
メモリ値は起動前の一時点の値であり、構築完了後の余力ではない。

| 項目 | clab02 の確認値 |
|---|---|
| Host kernel | `5.14.0-611.49.1.el9_7.x86_64` |
| CPU | `18` logical CPU（KVM guest。物理コア数ではない） |
| メモリ総量／利用可能 | 約 `122.34 GiB`／`118.32 GiB` |
| Swap | `4 GiB`、使用量 `0` |
| `/` の空き容量 | 約 `462 GiB`。確認した vrnetlab の作業ディレクトリも同一 filesystem |
| 稼働コンテナ | `0` |
| 保存済み NX-OS イメージ | `vrnetlab/cisco_n9kv:10.6.4.M.lite`（image ID `2691f049d3c4`）の追加を確認。`10.5.4.M.lite` も保持 |
| 保存済み kind イメージ | `kindest/node:v1.34.3`。topology 指定の digest 固定 `v1.35.5` は事前準備が必要 |

single-site は別ホスト clab01 で稼働しているため、clab01 の checksum timer は維持する。
clab01 の検証済み kernel は `5.14.0-611.27.1.el9_7.x86_64` で、clab02 とは異なる。
kind が共有するのは実行ホストの kernel なので、NX-OS 更新とは別に
[helper・実通信の判定](../runbooks/kernel-compatibility-policy.md) を clab02 で行う。
同名の `kind-adc-k02` context があっても、clab01 の kubeconfig／checksum state は流用しない。

## 2. 起動する構成の候補

[現行 topology](../../../nxos_multisite/nxos-fabric-multisite.clab.yaml) の有効な定義を集計した。
NX-OS は 1 台あたり `QEMU_MEMORY=4608` MiB、`QEMU_SMP=2` を設定している。

| 案 | 起動対象 | NX-OS | cEOS | Linux | Kubernetes Node | NX-OS の設定メモリ合計 |
|---|---|---:|---:|---:|---:|---:|
| 現行の全構成 | ADC／BDC／CDC、k01／k02／k03 | 21 | 7 | 11 | 9 | `94.5 GiB` |
| **今回作成：CDC 除外** | **ADC／BDC、k01／k02／k03** | **19** | **5** | **9** | **9** | **`85.5 GiB`** |
| 余力不足時の候補：CDC＋k01 除外 | ADC／BDC、k02／k03 | 19 | 5 | 9 | 6 | `85.5 GiB` |

Kubernetes Node は各クラスタの control-plane 1 台＋worker 2 台で数え、kind 管理用の topology ノードは含めない。
設定メモリ合計は QEMU のゲストメモリだけであり、QEMU 自体、cEOS、kind、Cilium、Tetragon、OS の使用量を含まない。
この数字だけで収容可能とは判定しない。

[過去の稼働記録](../../../nxos_multisite/README.md#リソース使用率) では、CDC の NX-OS 2 台が計約 `9.2 GiB`、
cEOS 2 台が計約 `3.0 GiB`。CDC 除外は計約 `12 GiB`、さらに k01 除外は約 `1.3 GiB` の削減相当になる。
これは旧構成の測定値からの概算で、今回の版・Cilium 導入後の削減量を保証する値ではない。
過去には clab02 の空きメモリが約 `3 GiB` で preflight に失敗している
（[過去の資源測定](../runbooks/resource-and-preflight.md#5-2026-08-29-の実行結果)）。

k01 の除外は必須ではない。前案は余力優先で除外を推奨したが、比較用途を優先して今回の YAML には残した。
起動時の一時的な増分と新しい kind／比較アプリの使用量は未測定のため、構築時に計測する。
Mesh の性能測定中は k01 の負荷試験を重ねず、CPU 競合による遅延・再送を分離する。
資源不足の場合は k01 除外も候補に戻すが、起動後の kind Node の単純な停止・再起動を前提にしない。

### 除外するもの・維持するもの

- CDC 除外対象：`cdc-bgw0101`／`cdc-bgw0102`、`cdc-l3sw0101`／`cdc-l3sw0102`、`cdc-cmsv01`／`cdc-cmsv02` と、それらに接続するリンク。
- k01 は維持：管理用の `adc-k01` と `adc-k01-control-plane`／`adc-k01-worker`／`adc-k01-worker2`、接続リンクを元版からそのまま保持。
- 維持対象：ADC／BDC の Fabric、DCI route-server 4 台、WAN の `p01`／`pe01`〜`pe04`、k02／k03 と試験用サーバ。

現行の [Cluster Mesh 設計](clustermesh-fabric-dci-and-acceptance.md) は **ADC k02 と BDC k03 の 2 クラスタ**である。
CDC には Cilium クラスタがなく、除外してもこの 2 クラスタ間の検証は構成上可能。
CDC のレガシーサイト接続・共有サーバへの到達性は試験対象から外す。k01 の MetalLB 比較は実施可能な構成を維持する。
「3 サイト構成」と「3 Cilium クラスタ」は別であり、将来の 3 クラスタ試験には追加設計が必要になる。

### 起動停止の実装案

CDC 除外版は **45 ノード定義・82 リンク**。3 サイト版との差は CDC の 6 ノード・20 リンクの除外で、
NX-OS イメージは両構成とも `10.6.4.M.lite` を指定する。`containerlab validate` は成功し、YAML の構造比較でも意図した差分に限定されることを確認した。
対応する [hosts-no-cdc.txt](../../../nxos_multisite/hosts-no-cdc.txt) は、残る NX-OS／cEOS 24 台の名前・管理 IP と一致する。
既存の config 投入手順では元の `hosts.txt` の代わりにこの台帳を選択する。
派生版の再生成スクリプトは追加していない。元版を変更した際は CDC 除外版との整合を再確認する。

最初から CDC を起動対象に含めないことで、起動時のピークも抑える。
派生版は元 topology と同じディレクトリに配置し、相対参照する config／kind 定義の解決先を維持した。
更新時も除外ノードへの参照がないこと、残すノードの名前・IP・interface・VLAN が変わらないことを検査する。
元版と縮小版は同じ lab を構成する選択肢とし、同時起動しない。

現行 containerlab の `--node-filter` は起動するノードの列挙であり、除外指定としては扱わない。
kind の管理用ノードと外部コンテナの依存もあるため、静的検査に加え、後続の構築時に新規起動を確認する。
除外先の BGP neighbor や port が保存 config に残る場合、その Down を縮小構成の期待値として台帳へ記録する。
共有 WAN や route-server をまとめて停止して削減しない。

CDC を必要時だけ稼働中の lab へ追加・停止する操作は、派生 YAML の切替だけで安全に再現できると決めつけない。
部分操作によるリンクの再作成、BGP 再収束、config 維持の確認は別途必要。
まず「CDC なしで新規構築できる版」を整え、動的な起動停止は次段階で扱う。

## 3. NX-OS 10.6(4)M の評価

Cisco の 10.6(4)M は 2026-08-17 公開で、Nexus 9300v／9500v 用のパッケージが記載されている。
修正一覧には Multisite BGW の Overlay Mroute 削除時のメモリリーク `CSCwu10926` がある。
更新候補とする理由にはなるが、このラボで同不具合が発生している証拠ではない。
[Cisco 公式リリースノート](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/release-notes/cisco-nexus-9000-nxos-release-notes-1064M.html)

10.6(x) の Lite ガイドでは、最小メモリ `4.5 GB` は basic bootup 向け、推奨は `8 GB`、
vCPU は最小 `2`／推奨 `4`。VXLAN EVPN、LACP、Multisite などの機能が記載されているが、
実際の構成に対する対応範囲とメモリを確認する必要がある。
現在の `4608 MiB`／`2 vCPU` を維持して少数台で評価し、さらに削減することは初期案に含めない。
[Cisco 公式 Lite ガイド](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/configuration/n9000v-9300v-9500v/cisco-nexus-9000v-9300v-9500v-guide-release-106x/m-nexus-9300v-and-9500v-lite-nx-os-image.html)

仮に各 VM を `8 GiB` にすると、縮小後も NX-OS 19 台だけで `152 GiB` となり clab02 には収まらない。
10.6(4)M への変更でメモリが減るとは見込まず、必要な役割で `4608 MiB` が不足するなら台数・ホスト配置を再設計する。

**ユーザーによる追加後、Docker に `vrnetlab/cisco_n9kv:10.6.4.M.lite` が存在することを確認した。**
イメージを起動して内部の版・機能を確認したわけではない。元 qcow2 の配布ファイル・checksum／build 記録の確認と、
代表構成での起動・動作確認を採用前の検証に残す。既存 10.5.4.M.lite は比較用に保持している。
vrnetlab のファイル名規則は `n9kv-<version>.qcow2`、build は `make docker-image` で、タグは入力の版に対応する。
今回の YAML は Docker 上で確認したタグを指定するが、動作確認済みとは扱わない。
[vrnetlab 公式 n9kv 手順](https://github.com/srl-labs/vrnetlab/blob/master/cisco/n9kv/README.md)

NX-OS VM の更新は clab02 の Linux kernel 更新ではない。Cilium の checksum 回避策の要否は別判定となる。
single-site の `TI-004` の遅延・再送や `TI-002` の経路課題も、新版で解消すると判断できる根拠はない。

## 4. 次の作業と判断条件

| 優先度 | 作業 | 完了・判断条件 |
|---|---|---|
| 完了：静的準備 | CDC 除外版と機器台帳を作成・検査 | CDC の 6 ノード・20 リンクを除外。k01 を含む残るノードの依存・名前・IP・interface を保持。起動は未実施 |
| 必須：起動前 | 保存 config の選択・投入方法を確定 | 現行 NX-OS の `startup-config` は両候補ともコメント、cEOS は `as-changes` を選択している。NX-OS も同じ AS 設計の保存設定を用い、空設定の起動を構築完了としない |
| 必須：起動前 | イメージとホスト preflight | kind `v1.35.5` の指定 digest と採用 NX-OS イメージを準備。kernel／helper、メモリ、ディスク、BTF 等を確認 |
| 推奨：新版採用前 | NX-OS 10.6(4)M Lite を代表構成で試す | 起動・版・config 読込、LACP／vPC、MTU、IPv4／IPv6、BGP／EVPN と代表的な BGW 動作を確認。1 台の起動成功だけでは完了にしない |
| 必須：構築時 | Fabric → kind → Cilium／観測基盤 → Mesh の順に測定 | 各段階の `MemAvailable`、swap、OOM、CPU、起動時間と収束を記録。Cilium 導入前は [既存 preflight](../runbooks/resource-and-preflight.md) を通す |
| 必須：通信試験前 | clab02 で checksum の要否と基盤疎通を確認 | 必要なクラスタのみ [専用 state・timer](../runbooks/checksum-compat-multisite.md) を登録。各サイトの LB／BGP／DNS／MTU を確認後、Mesh 接続・越境通信へ進む |
| 後続 | CDC を加える構成と起動停止を評価 | 余力を測り直し、部分起動停止後のリンク・経路・設定維持を確認してから手順化 |

資源の初期 gate は既存 preflight を維持する。今回の Mesh 用 2 クラスタ＋比較用 k01 の構成では、基盤導入後も
`MemAvailable` を最低 `8 GiB`、可能なら `12–16 GiB` 残すことを目標とする（今回の計画上の目安で、スクリプトの閾値変更ではない）。
swap 使用や OOM が出た状態で性能試験へ進まない。NX-OS 19 台の設定 vCPU 合計は `38` なので、
ホストの `18` logical CPU に対する競合も監視し、収束後の idle 負荷と通信負荷を分けて測る。
`--max-workers` は同時起動の負荷を抑える候補だが、定常メモリを減らす機能ではない。
現行 topology には最大 `2400` 秒の `startup-delay` もあるため、待ち時間と実際の起動失敗を分けて判定する。

採用する版を固定してから正式な基準値を記録する。10.6(4)M の機能・資源が不合格の場合は、
同じ縮小構成で保持した 10.5.4.M.lite を比較対象とし、構成差と版差を分離する。
