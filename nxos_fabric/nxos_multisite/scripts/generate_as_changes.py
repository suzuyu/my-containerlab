#!/usr/bin/env python3
"""Generate the separate-AS configuration set from configs/as-equals."""

from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "configs" / "as-equals"
DESTINATION = ROOT / "configs" / "as-changes"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def set_nxos_neighbor_local_as(
    text: str, neighbor: str, remote_as: int, local_as: int, label: str
) -> str:
    old = f"  neighbor {neighbor}\n    remote-as {remote_as}\n"
    new = old + f"    local-as {local_as} no-prepend replace-as\n"
    return replace_once(text, old, new, label)


def set_nxos_neighbor_remote_as(
    text: str, neighbor: str, old_as: int, new_as: int, label: str
) -> str:
    old = f"  neighbor {neighbor}\n    remote-as {old_as}\n"
    new = f"  neighbor {neighbor}\n    remote-as {new_as}\n"
    return replace_once(text, old, new, label)


def add_l3_common_rt(text: str, vrf: str, vni: int, label: str) -> str:
    pattern = re.compile(
        rf"(^vrf context {re.escape(vrf)}\n.*?)(?=^\S|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"{label}: VRF {vrf} not found")
    block = match.group(1)
    anchor = "    route-target both auto evpn\n"
    if block.count(anchor) != 2:
        raise RuntimeError(
            f"{label}: VRF {vrf} expected IPv4/IPv6 RT anchors, "
            f"found {block.count(anchor)}"
        )
    addition = (
        anchor
        + f"    route-target import 65000:{vni} evpn\n"
        + f"    route-target export 65000:{vni} evpn\n"
    )
    changed = block.replace(anchor, addition)
    return text[: match.start(1)] + changed + text[match.end(1) :]


def add_l2_common_rt(text: str, vni: int, label: str) -> str:
    old = (
        f"  vni {vni} l2\n"
        "    rd auto\n"
        "    route-target import auto\n"
        "    route-target export auto\n"
    )
    new = old + (
        f"    route-target import 65000:{vni}\n"
        f"    route-target export 65000:{vni}\n"
    )
    return replace_once(text, old, new, label)


def transform_bgw(path: Path, text: str) -> str:
    name = path.name
    text = text.replace("      rewrite-evpn-rt-asn\n", "")

    if name.startswith("adc-"):
        for neighbor in ("10.255.0.101", "10.255.0.102", "10.255.0.111", "10.255.0.112"):
            text = set_nxos_neighbor_local_as(
                text, neighbor, 65000, 64901, f"{name}:{neighbor}"
            )
        for neighbor in re.findall(
            r"^  neighbor (10\.255\.1\.\d+)\n    remote-as 64600$", text, re.MULTILINE
        ):
            text = set_nxos_neighbor_local_as(
                text, neighbor, 64600, 64601, f"{name}:{neighbor}"
            )
        for vrf, vni in (
            ("controller-vpc1", 9001),
            ("tenant1-vpc1", 19001),
            ("tenant2-vpc1", 29001),
        ):
            text = add_l3_common_rt(text, vrf, vni, name)
        text = add_l2_common_rt(text, 10100, name)
    elif name.startswith("bdc-"):
        for neighbor in ("10.255.0.101", "10.255.0.102", "10.255.0.111", "10.255.0.112"):
            text = set_nxos_neighbor_local_as(
                text, neighbor, 65000, 64911, f"{name}:{neighbor}"
            )
        for neighbor in re.findall(
            r"^  neighbor (10\.255\.2\.\d+)\n    remote-as 64600$", text, re.MULTILINE
        ):
            text = set_nxos_neighbor_local_as(
                text, neighbor, 64600, 64602, f"{name}:{neighbor}"
            )
        for vrf, vni in (
            ("controller-vpc1", 9001),
            ("tenant1-vpc1", 19001),
            ("tenant2-vpc1", 29001),
        ):
            text = add_l3_common_rt(text, vrf, vni, name)
        text = add_l2_common_rt(text, 10100, name)
    elif name.startswith("cdc-"):
        text = add_l3_common_rt(text, "tenant2-vpc1", 29001, name)
        for forbidden in ("vni 9001", "vni 19001", "vni 10100"):
            if forbidden in text:
                raise RuntimeError(f"{name}: obsolete CDC {forbidden} remains")
    else:
        raise RuntimeError(f"unsupported BGW: {name}")
    return text


def transform_rs(path: Path, text: str) -> str:
    name = path.name
    overlap = (
        "route-map OUT-TO-CDC-AS-OVERLAP permit 10\n"
        "  set ip next-hop unchanged\n"
        "  set as-path replace 65001 with 65000\n"
    )
    text = replace_once(text, overlap, "", f"{name}:overlap route-map")
    text = text.replace(
        "      route-map OUT-TO-CDC-AS-OVERLAP out\n",
        "      route-map RETAIN-NEXT-HOP out\n",
    )
    text = text.replace("      rewrite-evpn-rt-asn\n", "")

    for neighbor, old_as, new_as in (
        ("10.255.255.11", 65001, 64901),
        ("10.255.255.12", 65001, 64901),
        ("10.255.255.21", 65002, 64911),
        ("10.255.255.22", 65002, 64911),
    ):
        text = set_nxos_neighbor_remote_as(
            text, neighbor, old_as, new_as, f"{name}:{neighbor}"
        )

    pe_neighbors = re.findall(
        r"^  neighbor (10\.255\.(?:10|20)\.\d+)\n    remote-as 64600$",
        text,
        re.MULTILINE,
    )
    if len(pe_neighbors) != 2:
        raise RuntimeError(f"{name}: expected two PE neighbors, found {pe_neighbors}")
    for neighbor in pe_neighbors:
        text = set_nxos_neighbor_local_as(
            text, neighbor, 64600, 64699, f"{name}:{neighbor}"
        )
    return text


def transform_pe(path: Path, text: str) -> str:
    name = path.name
    if name in {"pe01_run.txt", "pe02_run.txt"}:
        text = re.sub(
            r"^(   neighbor 10\.255\.1\.\d+ remote-as )65001$",
            r"\g<1>64601",
            text,
            flags=re.MULTILINE,
        )
        expected_site = 2
    elif name in {"pe03_run.txt", "pe04_run.txt"}:
        text = re.sub(
            r"^(   neighbor 10\.255\.2\.\d+ remote-as )65002$",
            r"\g<1>64602",
            text,
            flags=re.MULTILINE,
        )
        expected_site = 2
    else:
        return text

    text, rs_count = re.subn(
        r"^(   neighbor 10\.255\.(?:10|20)\.\d+ remote-as )65000$",
        r"\g<1>64699",
        text,
        flags=re.MULTILINE,
    )
    site_as = "64601" if name.startswith("pe0") and name in {"pe01_run.txt", "pe02_run.txt"} else "64602"
    site_count = len(re.findall(rf"remote-as {site_as}$", text, re.MULTILINE))
    if site_count != expected_site or rs_count != 2:
        raise RuntimeError(
            f"{name}: site replacements={site_count}, RS replacements={rs_count}"
        )
    return text


def transform(path: Path, text: str) -> str:
    if re.fullmatch(r"(?:adc|bdc|cdc)-bgw\d+_run\.txt", path.name):
        return transform_bgw(path, text)
    if re.fullmatch(r"(?:adc|bdc)-rs\d+_run\.txt", path.name):
        return transform_rs(path, text)
    if re.fullmatch(r"pe\d+_run\.txt", path.name):
        return transform_pe(path, text)
    return text


def main() -> None:
    source_files = sorted(SOURCE.glob("*/*_run.txt"))
    if len(source_files) != 28:
        raise RuntimeError(f"expected 28 source configs, found {len(source_files)}")

    for platform in ("cisco_n9kv", "arista_ceos"):
        (DESTINATION / platform).mkdir(parents=True, exist_ok=True)

    for source in source_files:
        relative = source.relative_to(SOURCE)
        destination = DESTINATION / relative
        rendered = transform(source, source.read_text()).rstrip() + "\n"
        destination.write_text(rendered)

    readme = DESTINATION / "README.md"
    readme.write_text(
        "# AS changes configuration set\n\n"
        "`as-equals` を基に、DCI WAN underlay、DCI EVPN、サイト内 Fabric の AS を分離した構成です。\n\n"
        "- DCI EVPN: ADC 64901 / BDC 64911 / CDC 64931 / RS 65000\n"
        "- DCI WAN underlay: ADC 64601 / BDC 64602 / CDC 64603 / RS 64699 / WAN 64600\n"
        "- 共通 EVPN RT: `65000:<VNI>`\n"
        "- CDC は VNI 29001 のみを収容し、VNI 9001 / 19001 / 10100 は含みません。\n"
        "- Cisco N9Kv設定はNexus 9000vへ投入し、EVPN Multi-Siteの基本動作を確認済みです。\n\n"
        "生成元と変換規則は `../../scripts/generate_as_changes.py` を参照してください。\n"
    )

    generated = list(DESTINATION.glob("*/*_run.txt"))
    if len(generated) != 28:
        raise RuntimeError(f"expected 28 generated configs, found {len(generated)}")
    print(f"generated {len(generated)} configs in {DESTINATION}")


if __name__ == "__main__":
    main()
