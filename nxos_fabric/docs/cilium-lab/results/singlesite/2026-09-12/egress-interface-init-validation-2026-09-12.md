# 2026-09-12 Egress interface 初期化 DaemonSet の統合試験

## 対象と実装

single-site `adc-k02` の `egress0` 初期化を構築手順へ統合し、clab01 で動作試験した。
前回の「k02 が停止中」という説明はローカル Docker での検索に基づく誤りだった。
実行ホストの 3 Node と Fabric は稼働しており、再 deploy は不要だった。

- [初期化 manifest](../../../../../nxos_singlesite/k8s_kind/k02/cilium/manifests/egress-interface-init/README.md) は
  ConfigMap の `nodes.json` と、処理を埋め込んだ独立 DaemonSet を使用する。
- [構築 helper](../../../../../scripts/cilium-lab/configure-egress-interface-init.sh) が全 Node のアドレス誤配置・所有 marker・
  host の依存コマンドを検査し、対象 label と manifest を収束させる。ConfigMap 変更時は rollout する。
- `converge-cilium-lab.sh --profile singlesite-final --apply` へ同 helper を組み込んだ。
  既存ラボでは helper だけを適用した。全体構築コマンドはオフライン render までを検証した。
- レビューで IPv6 DAD 判定を修正した。iproute2 JSON の `tentative`／`dadfailed` の真偽値と flags 配列の
  両方を検査する。別 interface の同一 IP は prefix が違っても重複として拒否する。
- 試験後は DaemonSet・ConfigMap・対象 label・`egress0` を常設として保持する。
  試験用 Policy・BGP 広報・Pod・echo サーバを撤去するよう [試験手順](../../../tests/egress-gateway-test-plan.md) を更新した。

## 初期化と変更反映

| 試験 | 結果 |
|---|---|
| 初回適用 | worker／worker2 の 2 Pod が Ready。control-plane には配置なし |
| アドレス・所有者 | worker は `.1`／`::1`、worker2 は `.2`／`::2`。dummy・owner alias・checkpoint を確認 |
| 60 秒の通常稼働 | ログ追加、Pod 再起動、アドレス変更なし |
| 同一設定の再 apply | Pod UID を維持 |
| 手動のアドレスずれ | 正規 IPv4 を一時削除し余分な IPv4／IPv6 を追加。35 秒後も自動修復せず、check は失敗 |
| 明示 rollout | 正規 IP を復旧し、余分な IP を削除。両 Node の check 成功 |
| ConfigMap 更新のみ | 35 秒後も Pod 内の設定・アドレスは変わらない |
| ConfigMap 更新後の rollout | 旧 IP を保持したまま、追加した IPv4／IPv6 を設定 |
| 元の ConfigMap へ helper で復帰 | 変更を検出して rollout し、追加 IP を削除 |
| owner alias 不一致 | helper は適用前に拒否。alias 復元後の check 成功 |

設定ずれ・追加 IP の試験は Egress Policy と専用 BGP 広報が存在しない状態で実施した。
使用した追加 IP は `172.16.24.250/32` と `fd21:0:0:24::fa/128` で、終了時に除去した。
定期修復は実装しておらず、手動変更からの復旧には helper の `--action restart` を使う。

## 通信と経路

通常／gw-a／gw-b から外部 3 サーバへ IPv4／IPv6 を比較した。
selected Pod と gw-a は別 Node に配置し、Node 間の転送を含めた。

| 試験 | 結果 |
|---|---|
| 通常／gw-a／gw-b の HTTP | 各 12/12 成功。対象・対象外 Pod、対象内・除外・CIDR 外の送信元が期待どおり |
| ICMP、IP 全長 9000 byte | 3 経路 × 2 family × 3 packet、18/18 応答 |
| UDP、IP 全長 9000 byte | 同じ 6 条件で 18/18 echo 成功 |
| IP 全長 9001 byte | ICMP は各条件でローカル拒否。UDP は各条件 3 回とも送信拒否 |
| TCP、8000 byte write、1 stream、1 Mbps 指定 | 6 条件とも送受信量一致・プログラムエラー 0 |
| Cilium BGP 広報 | worker／worker2 が所有する `/32`／`/128` を広報 |
| BGR 2 台 | 個別 IP の next-hop はそれぞれの所有 Node。集約も存在 |
| Leaf0103／0104 | Egress 個別・集約経路を受信し、既存 LB 経路も維持 |
| 管理側 eth0 | 各経路 55 秒の観測で、両 worker のフィルタ対象 packet は 0 |

9001 byte の拒否は Pod の経路 MTU `9000` によるローカル制限であり、WAN 上の PMTUD 試験ではない。
capture は 3 経路 × 2 Node × 2 interface の 12 本で、取得側の kernel drop はすべて 0。
高負荷 UDP、TCP 一括送信の再送、TI-004 の性能問題を解決した判定には含めない。

## 新規 Pod の初回通信

gw-a 選択中に新規 Pod を 3 個順番に起動し、それぞれ IPv4／IPv6 を 40 回ずつ測定した。
HTTP 240/240 件が成功し、全件で指定 Egress IP を確認した。接続 deadline は従来どおり 400 ms。
Endpoint watch、Pod の起動記録、両 worker と外部サーバの capture を取得した。

TI-006 の初回 timeout は再現しなかった。以前の失敗を上書きせず、原因未確定の `Open` を維持する。

## 撤去と最終状態

- Policy 撤去後の 12/12 HTTP は通常送信元へ復帰した。基本比較は合計 48/48 HTTP 成功。
  新規 Pod の 240 件と合わせた 288 件は、外部サーバの request ID・送信元とも機械照合した。
- 試験用 BGP 広報の撤去後、両 BGR と Leaf0103／0104 で Egress の個別・集約経路が消え、LB 経路は維持された。
- 試験用 namespace／Pod、Policy、広報、外部 3 サーバの一時待受 `19090`〜`19093` を撤去した。
  初期化 DaemonSet の 2 Pod、ConfigMap、対象 label、両 worker の `egress0` は保持した。
- Cilium `3/3`、Node `3/3` Ready、BGP `8` Established、API readyz 成功。
  Cilium の ConfigMap data と DaemonSet spec、agent の UID・再起動回数は変更前後で一致した。
- 既存 LB の Cluster／Local × IPv4／IPv6 × 3 回は、変更前後それぞれ 12/12 HTTP 成功。
- 全 3 Node の Fabric 12 interface は MTU `9150`、管理側は `1500`。
  Pod の経路 MTU `9000`、両 worker の VXLAN checksum off も維持した。

静的検証は全体構築の check-only render、Bash 構文、差分の空白検査に成功した。
IPv6 DAD の JSON 形式 6 条件もオフライン試験に成功した。
公開 config は 122 ファイルを検査し、変更 0、username 該当 0、global endpoint／秘密鍵の検出なし。
既存の使い捨てラボ用 SNMP／NTP／logging 設定 530 行を保持した。

## 証跡と検証範囲

セッションは `egress-init-ypOuk9eg`。Git 管理外の
`nxos_fabric/nxos_singlesite/operations/cilium-lab/2026-09-12/adc-k02/raw/` 配下に保存する。
最初の通信集計は JSON の項目名を `recv_bytes` と誤記して停止した。通信ログは `instrument-first/` に保持し、
正しい `received_bytes` へ修正して全 3 経路を再測定した。この停止は通信障害として数えない。
準備用 Python の構文エラーは修正して実行した。エラー時には準備操作を開始していない。

Node／host 再起動、Leaf の startup-config 保存、kernel 更新、multisite 起動、TI-002 の ECMP 障害試験、
高負荷・SNAT port 枯渇は実施範囲に含めない。Node 起動時の再作成は、次の再起動試験で確認する。
