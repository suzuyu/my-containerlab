# my-containerlab

個人のcontainerlab検証環境を保存するリポジトリです。構成や設定は検証時点のものであり、
本番利用、完全性、可用性、安全性を保証しません。

## Lab

- `nxos_fabric/nxos_singlesite`: Cisco Nexus 9000vによるEVPN/VXLAN Single Site
- `nxos_fabric/nxos_multisite`: Cisco Nexus 9000vによるEVPN Multi-Site (一部スイッチ・ルータとして Arista cEOS も使用)

Cisco N9Kv、Arista cEOS、その他のcontainer imageはこのリポジトリに含みません。利用者が各製品の
ライセンスと配布条件に従って用意してください。MetalLB本体のmanifestも同梱せず、各labの手順で
versionを固定して公式配布元から取得します。

## Security

公開configでは`username`設定を除去し、containerlab imageのlab用default credentialを利用します。
SNMP community、SNMP／NTP／logging先はprivate network内の使い捨てサンプルです。同じ値を別環境で
再利用しないでください。runtime artifact、収集ログ、credential、private keyはGit管理対象外です。

## License

このリポジトリ自身の文書、script、lab設定は[MIT License](./LICENSE)で提供します。参照または取得する
第三者ソフトウェアとimageには、それぞれのライセンスが適用されます。
