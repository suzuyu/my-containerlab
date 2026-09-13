# multisite k02 の初回導入・基本確認

## 結論と実施範囲

2026-09-13、実行環境 clab02 の CDC 除外版で、起動済みの `adc-k02` に
[k02 README](../../../../../nxos_multisite/k8s_kind/k02/cilium/README.md) のパターン A を適用した。
Cilium、CoreDNS upstream、LB IPAM／BGP、Cluster Mesh API、Hubble、Tetragon の導入と
k02 内の基本通信確認を完了した。k01／k03 の設定変更、Node 再起動、NX-OS の設定投入は行っていない。

**Cluster Mesh 全体は未受入**。k03 の導入と共通 CA の準備・接続が残り、
`cilium status` は k03 に関する controller error を表示する。
BGP は初回 ARP／ND 解決の問題を伴ったため、無介入での初期化成功とも判定しない。

## 適用内容と到達状態

| 項目 | 適用・確認結果 |
|---|---|
| Kubernetes | `v1.35.5`、Node 3/3 Ready |
| Node InternalIP | control-plane `172.16.4.11`／`fd21:0:0:4::1:1`、worker `172.16.4.21`／`fd21:0:0:4::2:1`、worker2 `172.16.4.22`／`fd21:0:0:4::2:2`。Fabric IP へ再設定 |
| Node NIC | `eth1`／`eth2`／bond／Fabric VLAN の MTU `9150` を確認。管理 `eth0` は `1500` |
| Cilium | chart `1.20.1`、Helm revision 1 deployed、agent／Envoy 各 3/3、operator 1/1 |
| Cilium values | `00-base.yaml`、`10-observability.yaml`、`20-multisite-clustermesh.yaml`、生成した `runtime/10-k8s-api.yaml` を適用 |
| API bootstrap | Node 内から到達できる `172.18.0.6:6443` を生成値に設定。全 Node から `/livez` を確認 |
| MTU | Cilium 基準 `9050`、一時 Pod の interface `9050`、別 Node の Pod 宛 IPv4／IPv6 経路 `9000` |
| CoreDNS | host resolver `192.168.129.254` を Pod から検証して upstream に適用。外部名の直接 DNS／Cluster DNS 解決成功、2/2 Ready |
| BGP | worker 2 台のみを speaker に指定。BGR01／02 との IPv4／IPv6 計 8/8 Established |
| LB IPAM／BGP resource | `resources/10-lb-ipam.yaml`、`20-bgp.yaml`、`21-bgp-planned-shut.yaml` を適用。maintenance label は未設定 |
| 集約用経路 | 両 worker に `172.16.14.0/26`、`fd21:0:0:14:0:0:1:0/112` の blackhole route、metric `42760` を適用 |
| Mesh API | `resources/30-clustermesh-apiserver-service.yaml` を適用。2/2 replica Ready、PDB `minAvailable: 1`、Service affinity `ClientIP` |
| Mesh API VIP | `172.16.14.10`／`fd21:0:0:14:0:0:1:10`。BGR01 の `/32`／`/128` 経路は両 worker を next-hop とする |
| Hubble | Relay／UI Ready、Hubble の接続 Node 3/3、flow の取得を確認。ブラウザによる UI 操作は未確認 |
| Tetragon | chart `1.7.0`、Helm revision 1 deployed、agent 3/3、operator 1/1。observe-only の標準値を適用 |
| 未有効化の機能 | Egress Gateway／Egress 初期化、WireGuard、MCS API、Tetragon enforcement は標準設計どおり未適用 |

適用元の values／resources は `nxos_fabric/nxos_multisite/k8s_kind/k02/cilium/` 配下。
CoreDNS の採用値は同ディレクトリの `runtime/20-coredns-upstream.env` に記録した。

## 基本通信の確認

専用 namespace `cilium-k02-bootstrap-check` に両 worker の HTTP backend と client を作成した。
外部 client は `adc-t1sv0101` の Fabric 側を使用した。

| 確認 | 結果 |
|---|---|
| 導入後 preflight | PASS 78、WARN 0、FAIL 0 |
| Cilium health | 3/3 reachable。Node／health endpoint の IPv4／IPv6、ICMP／HTTP が成功 |
| Pod 間 HTTP | 同一 Node・別 Node × IPv4／IPv6、4/4 成功 |
| ClusterIP HTTP | backend 2 台 × IPv4／IPv6、4/4 成功 |
| 外部 NodePort HTTP | 同一 Node・別 Node の backend を含む IPv4／IPv6、8/8 成功 |
| 外部 LoadBalancer HTTP | backend 2 台 × IPv4／IPv6 × 5 回、20/20 成功。BGP 復旧後にも 8/8 成功 |
| IPv6 TCP 受信 checksum | NodePort 17 packet、LB 43 packet が correct、不正 0。受信方向のみを判定 |
| 撤去 | 一時 namespace と Pod／Service／LB を撤去。常設 Mesh API VIP と BGP は維持 |

Pod 直接通信の最初の試行は誤って port `80` を指定し、接続拒否となった。
manifest の待受 `8080` に合わせた再試行が上表の 4/4。最初の失敗も証跡に保持した。
MTU は経路値までの確認であり、`9000`／`9001` byte の ICMP 境界試験は
Node に `ping` がなく実行できていない。全体 connectivity、性能、障害復旧、DCI 越しの試験は未実施。

## 発見した問題と対応

### 1. kubeconfig のアクセス権

containerlab の出力 kubeconfig は所有者と ACL mask の組合せにより作業ユーザーから読めなかった。
control-plane 内の管理用 kubeconfig から、Git 管理外の専用コピーを mode `600` で作成した。
API の host 側公開 port と context を設定して使用した。出力元の ACL は変更していない。

同じホストで操作を継続する場合は以下を使用する。再構築時は API 公開 port の再確認が必要。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export LAB_ROOT="${REPO_ROOT}/nxos_fabric/nxos_multisite"
export K8S_CLIENT_RUNTIME="${LAB_ROOT}/k8s_kind/client/runtime"
export PATH="${K8S_CLIENT_RUNTIME}/bin:${PATH}"
hash -r
export KUBECONFIG="${LAB_ROOT}/k8s_kind/k02/cilium/runtime/kubeconfig-k02"
export KUBE_CONTEXT="kind-adc-k02"
kubectl --context "${KUBE_CONTEXT}" get nodes
```

### 2. Node IP の未反映と古い MTU 検査値

NIC の Fabric IP／MTU は正しかったが、全 Node の kubelet は管理 IP を使用していた。
既存の `configure-kubelet-node-ip.sh` を Node ごとの Fabric IPv4／IPv6 で再適用し、
kubelet のみを再起動した。Node／CiliumNode のアドレスを確認した。
deploy 後に未反映となった原因は未特定であり、新規構築時の確認項目として残す。

`preflight-host-and-kind.sh` に旧 MTU `9100` の比較が 3 箇所残っていたため、
現行設計の `9150` に修正した。修正前の失敗ログを保持し、導入後は 78 件すべて成功した。

### 3. worker2 と BGR01 の初回 ARP／ND 解決

BGP は最初 6/8 Established。worker2 の BGR01 `172.16.4.4`／`fd21:0:0:4::4` が
ARP／ND INCOMPLETE で、BGR01 側にも worker2 の隣接情報がなかった。
BGR01 から worker2 への IPv4／IPv6 ping はそれぞれ初回 timeout、続く 2 回が成功し、
隣接情報の学習後に BGP は 8/8 Established となった。

NX-OS の設定変更、ARP／BGP clear は行っていない。
[k01 の調査](k01-metallb-neighbor-investigation.md) と同様の症状であり、
逆方向 ping は診断時に復旧を促した操作であって恒久対策ではない。
Fabric 側の初回 ARP／ND 転送経路と再現条件の調査が残る。

### 4. checksum 回避策の採否

host kernel は `5.14.0-611.49.1.el9_7.x86_64`。
helper probe は flags `0`／`16` が成功、`144` が `-22` で、対象 helper の IPv6 flag は未対応だった。
ただし今回の NodePort／LB 試験では通信成功と正しい受信 checksum を確認したため、
両 worker の `cilium_vxlan tx-checksum-ip-generic` は `on` を維持した。
k02 用の checksum state／timer は作成していない。

この結果は試験した経路と設定の範囲に限る。k03／DCI 越しの確認で症状が出た場合は
[multisite checksum 手順](../../../runbooks/checksum-compat-multisite.md) に従って再評価する。

### 5. k03 接続待ちとメモリ

`cilium status` の 6 errors は各 Node の `remote-etcd-bdc-k03` 関連。
Mesh API 自体は Ready だが、k03 接続は agent `0/3`、KVStoreMesh `0/2`。
k03 の導入、CA 共有、名前解決／VIP 到達性と証明書を含む接続確認を次に行う。

host の MemAvailable は導入前約 `22.5 GiB`、基本確認時約 `17.2 GiB`。
swap 使用は `0`。これは一時 Pod を含む時点の実測で、将来の負荷余裕を保証するものではない。
k03 の導入前後と Cluster Mesh 試験中に再測定する。

## 証跡

Git 管理外の `nxos_fabric/nxos_multisite/operations/cilium-lab/2026-09-13/k02-initial-install/` に
preflight、導入ログ、Node／CiliumNode、BGP、HTTP 結果、受信 capture、MTU 経路値、
Cilium／Mesh／health 状態、メモリ測定と一時 manifest を保存した。
秘密情報を含み得る Helm render と kubeconfig は公開しない。
