# Egress UDP 遅延診断

既存の `egress-probe server` の UDP echo に対し、送信番号・実行 ID・送信時刻を含む packet を送る。
各応答の RTT、順序逆転、重複、payload 不一致と、観測終了時点の未回収数を記録する。
`missing_at_observation_end` は有限時間内の未回収数であり、それだけで経路上の破棄を確定しない。

```bash
CGO_ENABLED=0 go build -o /tmp/egress-latency-probe main.go
go test main.go main_test.go
/tmp/egress-latency-probe udp4 172.16.0.2:19092 5 1200 1 5
/tmp/egress-latency-probe udp6 '[fd21:0:0:1::102]:19092' 5 1200 1 5
```

引数は network、宛先、送信期間（秒）、UDP payload（byte）、目標送信量（Mbps）、
送信期間終了後の観測時間（秒）。IPv4／IPv6 は別々に測る。server は受信した datagram を変更せず返す必要がある。

- `received_by_legacy_cutoff`：送信期間終了 + 500 ms までに受信した一意な応答数。
- `received_late`：その後、指定した観測終了時刻までに受信した一意な応答数。
- `missing_at_observation_end`：送信数から上記 2 種類の応答数を引いた数。
- `actual_send_mbps`：実際の送信 payload 量を指定送信期間で割った値。ヘッダー・往復の帯域は含まない。
- `packets`：各送信番号の送受信時刻と RTT。capture と実行 ID・送信番号で照合する。

送信の遅れを取り戻すための連続送出を抑えているため、従来の `egress-probe load` と pacing が異なる。
両者の結果を比較する際は、目標 Mbps だけでなく実測 Mbps／packet 数と burst の違いも記録する。
受信 socket buffer、MTU、PMTUD、offload の設定は変更しない。終了コード 0 だけで成功判定せず、
未回収数・遅延・payload 不一致と capture の取得側 drop を照合する。

単体試験は遅延・重複・順序逆転の集計と、異なる実行 ID・切れた payload の拒否を確認する。
