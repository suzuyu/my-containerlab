# k02／k04 upgrade rehearsal helpers

[手動手順](../../../docs/cilium-lab/tests/upgrade-rehearsal-runbook.md)に従って操作する。
実機へ接続するスクリプトであり、repository root で `env.sh` を source してから使う。
`lab.py` は操作を一段階ずつ明示する。自動の全工程実行や startup-config 保存は行わない。

| ファイル | 用途 |
|---|---|
| `app.py` | echo、外部 API 呼出し、業務 gate、外部送信元記録と小規模受付 mock |
| `render.py` | 試験専用 Kubernetes resource の生成。k02 の既存 Pool を再利用 |
| `lab.py` | snapshot、apply、rank、gate、専用 IP／Policy、Nexus 差分、cleanup、復元照合 |
| `observers.py` | 既存 ADC 端末の network namespace を共有する一時 mock／monitor |
| `monitor.py` | 固定条件の HTTP 測定。再試行なし、JSONL 保存 |
| `check.py` | ADC／BDC、両 AF、VIP／NodePort の個別確認 |
| `egress-check.py` | 業務停止中も実施できる副作用のない外部 probe |
| `health.py` | 復元後の Cilium／Mesh／BGP と全 Agent の health 確認 |
| `summarize.py` | HTTP 失敗、期待応答、確認時刻、停止から復帰までの時間を分離して集計 |

実行時の raw config・values・ログ・台帳は `operations/` に保存する。
試験用 IP の単独所有と開始前 snapshot を前提とし、他環境へそのまま適用しない。
