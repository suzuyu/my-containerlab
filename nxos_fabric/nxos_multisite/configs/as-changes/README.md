# AS changes configuration set

`as-equals` を基に、DCI WAN underlay、DCI EVPN、サイト内 Fabric の AS を分離した構成です。

- DCI EVPN: ADC 64901 / BDC 64911 / CDC 64931 / RS 65000
- DCI WAN underlay: ADC 64601 / BDC 64602 / CDC 64603 / RS 64699 / WAN 64600
- 共通 EVPN RT: `65000:<VNI>`
- CDC は VNI 29001 のみを収容し、VNI 9001 / 19001 / 10100 は含みません。
- Cisco N9Kv設定はNexus 9000vへ投入し、EVPN Multi-Siteの基本動作を確認済みです。

生成元と変換規則は `../../scripts/generate_as_changes.py` を参照してください。
