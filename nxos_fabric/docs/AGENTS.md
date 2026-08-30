# Documentation Instructions

## Scope

このファイルは、`nxos_fabric/docs/` 以下の Markdown 文書に適用する。
リポジトリルートの `AGENTS.md` にある安全規則と公開規則も引き続き適用する。

## Japanese and ASCII Spacing

- Markdown の本文、見出し、箇条書き、表、リンク表示文字では、日本語と半角英数字の境界に
  半角スペースを 1 つ入れる。
- 製品名、略語、バージョン、単位、数字、inline code も半角英数字側として扱う。
- 日本語の句読点や括弧との境界には、この規則だけを理由とする空白を追加しない。
- 既存文書を編集するときは、変更対象の文または段落をこの規則へ合わせる。依頼と無関係な文書全体の
  一括整形は別変更として扱う。

推奨例:

- `Cilium を使用する。`
- `Stage 1 で確認する。`
- `IPv4 と IPv6 を個別に確認する。`
- `` `kubectl` を実行する。``
- `3 ノードの構成とする。`

避ける例:

- `Ciliumを使用する。`
- `Stage 1で確認する。`
- `IPv4とIPv6を個別に確認する。`
- `` `kubectl`を実行する。``

## Exceptions

次の内容の内部は空白を追加または削除せず、構文と実際の値を維持する。

- fenced code block と inline code の内部。ただし、inline code の外側と日本語の境界には半角スペースを入れる
- URL と Markdown link destination
- YAML、JSON、shell、設定例、出力例

ファイル名、パス、command、option、resource 名、識別子、image tag、digest、IP address、CIDR、
port、protocol の値は、本文中では原則として inline code で表記する。
