# k02／k04 反復試験用の一時 BGR Config

対象は ADC BGR `0101`／`0102`。両台に同じ差分を使用する。
[手順書](../../../../docs/cilium-lab/tests/upgrade-rehearsal-runbook.md)の snapshot・前提照合後に適用する。

- `bgr-apply.cfg`：P の rank → LP、新側の試験 E exact route の受信許可。
- `bgr-restore.cfg`：開始前 inbound map へ戻し、`UREH_*` 定義を撤去。

既存 map が想定と異なる場合はそのまま使わない。startup-config への保存は行わない。
BGW／Leaf の追加変更、Node 保守用 community の操作は含まない。
