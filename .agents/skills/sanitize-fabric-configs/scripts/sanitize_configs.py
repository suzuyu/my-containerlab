#!/usr/bin/env python3
"""Sanitize public network config samples and check publication blockers."""

from __future__ import annotations

import argparse
import ipaddress
import re
from pathlib import Path


USERNAME_RE = re.compile(r"^\s*!?\s*username\s+", re.IGNORECASE | re.MULTILINE)
PRIVATE_KEY_RE = re.compile(r"BEGIN [A-Z0-9 ]*PRIVATE KEY", re.IGNORECASE)
ENABLE_SECRET_RE = re.compile(r"^\s*enable\s+secret\b", re.IGNORECASE | re.MULTILINE)
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6_RE = re.compile(
    r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}"
    r"(?![0-9A-Fa-f:])"
)
SAMPLE_MANAGEMENT_RE = re.compile(
    r"^\s*(?:snmp-server|ntp\s+server|logging\s+server)\b",
    re.IGNORECASE | re.MULTILINE,
)
OMISSION = "! credential lines omitted from public lab sample\n"


def is_runtime_or_backup(path: Path) -> bool:
    return any(
        part in {"operations", "raw", "logs", "tmp"}
        or part.startswith("clab-")
        or ".bak" in part
        for part in path.parts
    )


def config_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.glob("**/configs/**/*")
        if path.is_file()
        and path.suffix in {".cfg", ".txt"}
        and not is_runtime_or_backup(path)
    )


def sanitize_username_blocks(text: str) -> tuple[str, int]:
    output: list[str] = []
    in_username_block = False
    omitted_blocks = 0

    for line in text.splitlines(keepends=True):
        if USERNAME_RE.match(line):
            if not in_username_block:
                output.append(OMISSION)
                omitted_blocks += 1
            in_username_block = True
            continue
        in_username_block = False
        output.append(line)

    return "".join(output), omitted_blocks


def global_ip_addresses(text: str) -> list[str]:
    findings: set[str] = set()
    for candidate in IPV4_RE.findall(text) + IPV6_RE.findall(text):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_global and not address.is_multicast:
            findings.add(candidate)
    return sorted(findings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("nxos_fabric"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    files = config_files(args.root)
    if not files:
        print(f"ERROR: no config files found below {args.root}")
        return 2

    changed_files = 0
    omitted_blocks = 0
    management_directives = 0
    errors: list[str] = []

    for path in files:
        original = path.read_text()
        rendered, blocks = sanitize_username_blocks(original)
        omitted_blocks += blocks

        if args.write and rendered != original:
            path.write_text(rendered)
            changed_files += 1

        checked = rendered if args.write else original
        if USERNAME_RE.search(checked):
            errors.append(f"{path}: username configuration remains")
        if PRIVATE_KEY_RE.search(checked):
            errors.append(f"{path}: private key material remains")
        if ENABLE_SECRET_RE.search(checked):
            errors.append(f"{path}: enable secret remains")
        for address in global_ip_addresses(checked):
            errors.append(f"{path}: globally routable IP address {address}")
        management_directives += len(SAMPLE_MANAGEMENT_RE.findall(checked))

    action = "sanitized" if args.write else "checked"
    print(f"{action} {len(files)} config files")
    print(f"changed files: {changed_files}")
    print(f"username blocks requiring omission: {omitted_blocks}")
    print(f"retained sample management directives: {management_directives}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        if not args.write and omitted_blocks:
            print("ERROR: run again with --write to omit username configuration")
        return 1

    print("publication config checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
