# Repository Instructions

## Scope

このファイルはリポジトリ全体に適用する。このリポジトリは個人の containerlab 検証環境を
保存するためのものであり、本番環境向けの設定例や動作保証を提供するものではない。

## Safety

- 実機またはlabへの接続、`containerlab deploy`、config投入、`write memory`、lab破棄は、
  ユーザーが対象と操作を明示した場合だけ実行する。
- `operations/`、`raw/`、`logs/`、`clab-*`、backup、credential inventory、private key、
  support bundleをcommitしない。
- ユーザーの未コミット変更を保持し、依頼と無関係なファイルを変更しない。
- branch作成、commit、push、Pull Request作成は、ユーザーが該当するGit操作を明示した場合だけ行う。

## Publication checks

`nxos_fabric/`の追加、commit、push、公開前、および公開config再生成後は
[sanitize-fabric-configs](.agents/skills/sanitize-fabric-configs/SKILL.md)を使用する。

- 公開configからactive／commentedを問わず`username`設定行を除去する。
- SNMP community、SNMP／NTP／logging先は、使い捨てのlabサンプルで、宛先が非global addressの
  場合だけ保持できる。別環境で再利用している値は公開前に変更する。
- secret値、未加工の認証情報、実機ログを報告やcommit messageへ転載しない。

## Maintained transformations

- `nxos_fabric/nxos_multisite/scripts/generate_as_changes.py`は、`as-equals`から`as-changes`を
  再生成する正規の変換スクリプトとしてGitへ含める。実行後は公開前サニタイズを再実行する。
- `standardize_nxos_management.py`はHomeLab固有値を上書きするローカル一括変換としてignoreを維持する。
- README、`hosts.txt`、topology、configのホスト名、管理IP、手順を変更範囲内で一致させる。
