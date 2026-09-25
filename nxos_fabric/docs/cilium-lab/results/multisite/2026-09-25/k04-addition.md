# k04 の Kubernetes 1.36.4 追加

2026-09-25 実施。ユーザーは既存 lab への追加試行と k02 の通信影響を許容した。
全 lab の停止・再作成は今回の操作に含めない。

## 実施範囲

- containerlab `0.78.2`／内蔵 Kind `0.31.0` を使用。
- k04 は `kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed` で初回作成。
- 既存 Leaf 4 台の再作成、k04 の 3 Node と 6 リンクを追加。
- Leaf／BGR の `10-connectivity` を使用。Cilium／Mesh 導入、アプリ VIP・Egress IP の切替は未実施。

## 追加前の確認と差分適用

1. ホストの MemAvailable 約 11 GiB、ディスク空き約 348 GiB。k02／k03 は各 3 Node が Ready。
2. Leaf 4 台・BGR 2 台の running／startup 設定を非公開領域へ退避。
   既存 k02／k03 の Helm values、kubeconfig、Cilium CA も保存した。
   使用する Leaf ポートは shutdown、VLAN／VNI／Port-channel の新規割当は未使用だった。
3. SUID 付き containerlab の直接実行で dry-run が成功。先の `sudo -n` の認証失敗とは区別する。
4. 完全版 topology では、既存 Kind の作成用定義まで `added-nodes` に入った。
   `adc-k01`／`adc-k02`／`bdc-k03` の作成用定義だけを除外し、既存 Node コンテナと全リンクを残した追加用 topology を生成。
5. 最終計画は新規 k04 の 4 定義、再作成 Leaf 4 台、削除なし。
   リンクは新規 6 本と Leaf に接する既存 40 本を張り直す計画だった。
6. Leaf の起動設定に「退避した running 設定＋k04 差分」を指定し、追加用 topology を適用。
   `--reconfigure`／`--node-filter` は使わず、終了コード `0` を確認した。

## 追加後に必要だった対応

| 事象 | 対応・確認 |
|---|---|
| Port-channel149 所属の Ethernet1/49–50 に VLAN 追加を重ねると NX-API が拒否 | 所属物理ポートへの重複投入行を削除。Port-channel149 だけで VLAN 106 を追加。BGR 2 台の修正版 51 コマンドが受理された |
| k04 の生成 kubeconfig が root 所有 | ユーザー所有の `k8s_kind/k04/kubeconfig-k04` を mode 600 で書き出した |
| k04 初回 API 証明書に localhost の SAN がない | 証明書に含まれる Docker 側 IP の `6443` で接続。TLS 検証は維持。次回作成向け Kind 定義には localhost の SAN を追加 |
| 既存 Linux／Kind Node の eth1／eth2 が bond から外れる | 影響した既存 12 コンテナに、従来 topology のネットワーク初期化コマンドを再実行 |
| 対向 VM の tc redirect が消失・旧 ifindex を参照 | ADC Spine 2 台の各 eth1–4、BGR 2 台の各 eth49–52、計 16 ポートの eth–tap 双方向 redirect を復旧 |

## 受入状況

k04 の追加作成と Fabric 接続は成功。全 lab の停止・再作成は行わなかった。
ただしリンク張り直し後の手動復旧を伴い、無介入での追加・復帰成功とは扱わない。

| 確認項目 | 結果 |
|---|---|
| k04 の Kubernetes API | 3 Node とも `v1.36.4`、Fabric 側 IPv4／IPv6 を確認 |
| 既存コンテナ | 変更された ID は予定した Leaf 4 台のみ。既存コンテナの消失なし |
| k02／k03 | 各 3 Node が Ready、Kubernetes `1.35.5` を維持 |
| Leaf 4 台 | 全台 healthy、全 Port-channel が Up、各 7 NVE peer が Up |
| BGR の追加設定 | 両台の Port-channel149 と Ethernet1/49–50 は `103-104,106`、IPv4／IPv6 peer 計 4 個ずつを確認 |
| k04 → SVI／BGR 2 台／k02・k03 worker 2 台ずつ | 全 3 Node・両 AF の ICMP `42/42` 成功 |
| k02／k03 → 自クラスタ SVI／対向 worker 2 台 | 全 6 Node・両 AF の ICMP `36/36` 成功 |
| 既存クラスタ間の Node／health endpoint HTTP | 全 6 Node から対向 3 Node の IPv4／IPv6 へ `72/72` 成功 |
| 既存 Cilium／Mesh | 両クラスタの status 正常、Mesh agent `3/3`・KVStoreMesh `2/2` が両方向で接続 |
| 既存 BGP の最終状態 | k02／k03 とも `8/8 Established` |
| Cilium health 最終表示 | 全 6 Agent × 6 Node × Node／health endpoint × 両 AF × ICMP／HTTP、`288/288` 成功 |
| k04 Cilium／Mesh | 未導入。3 Node の NotReady は CNI 未設定による想定状態 |

最初の Fabric probe は `72/78` で、k04 → BGR01 の両 AF 計 6 経路が失敗した。
Leaf 0101 の vPC delay-restore 中は BGR01 の Port-channel149 が down、Vlan106 も down だった。
タイマー終了・LACP 復帰後は追加設定変更なしで `78/78` に収束した。

k02 の BGP は一旦 `7/8 Established`。worker2 の BGR01 向け IPv6 neighbor が `INCOMPLETE` で、
BGR01 から対象 Node へ限定 ping を行うと、初回 timeout 後に 2 回成功して隣接が解決した。
[先行復旧](pre-coexistence-recovery.md)と同様の手動介入として残し、無介入復帰の合格とはしない。
Cilium health の表示には停止中の古い失敗結果も残ったため、更新時刻と実送信の HTTP probe を分けて確認した。
最終確認では表示も `288/288` 成功へ収束した。最終受入の採取時刻は 2026-09-25 12:47:45 JST。

アプリの Global Service／LB、Egress、性能・障害試験は今回再実施していない。
本結果は基盤追加の受入であり、アップグレード試験や Stage 5 全体の合格へ読み替えない。

## 起動時間と停止影響

時刻は JST。11:38 に追加 deploy を開始し、11:39:32 に containerlab が終了した。
Leaf 0103 は 12:16、0104 は 12:17 頃に起動設定の投入を完了した。
Leaf 0101／0102 は 12:22 頃に NX-OS の System ready、12:29 頃に設定投入へ進み、
12:40:50 までに全 Leaf の healthy を確認した。通信の収束確認はその後に実施した。
ホストの利用可能 CPU は 18、起動中の load average は約 34。MemAvailable は約 10 GiB、swap 使用は 0 だった。
containerlab の処理時間と、NX-OS VM の初回起動・vPC／NVE の収束時間は分けて見積もる。
Leaf 起動中は既存 k02 の worker2 到達性と Mesh に影響し、API 上の Ready 維持だけでは復旧を示さなかった。

## 保存状態と次の作業

Leaf の起動処理は running-config を startup-config へ保存して完了する。
BGR 2 台の追加分は running-config に適用済みだが、今回 startup-config への保存操作は実施していない。
この追加作業時点では未保存だったが、[後続の Cilium／Mesh 導入](k04-clustermesh.md)で両 BGR の保存・照合を完了した。
再作成時は `10-connectivity` の再適用が必要。
公開 topology へ稼働中の認証情報を含む設定を埋め込んでいないため、全体再構築では追加 Config の投入が別途必要。

この後、k04 の Cilium／Tetragon 導入、Mesh API のみの BGP 広告、k02／k03 との Mesh 接続と
NodePort 検証を上記の後続記録で実施した。今回アプリ VIP／Egress IP の広告・移管は開始していない。

## ファイル検査

`git diff --check` は成功。公開 Config のサニタイズ検査は 140 ファイルを対象に成功し、
要修正ファイル・username 除去対象はいずれも 0。既存の使い捨て lab 用 SNMP／NTP／logging 等の
管理サンプル設定 530 件を保持した。生ログ・実機認証情報は公開ファイルへ転記していない。

## 証跡と再実行時の注意

生ログ・退避設定・起動用統合設定は Git 対象外の
`nxos_fabric/nxos_multisite/operations/k04-add-20260925-113255/` に保存した。
認証情報を含み得るため公開 Config へコピーしない。
`.k04-add.runtime.clab.yaml` は既存状態に依存した一回の追加用であり、全体再構築や destroy の入力として流用しない。
後続操作は改めて差分を確認し、既存 Kind の作成用定義が誤って再追加されないようにする。

[k04 構築手順](../../../../../nxos_multisite/k8s_kind/k04/cilium/README.md)
