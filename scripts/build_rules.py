#!/usr/bin/env python3
"""Build XBoard templates and public rule links from one ACL4SSR revision."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ACL_RAW = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR"
ACL_API = "https://api.github.com/repos/ACL4SSR/ACL4SSR/commits/master"
CONFIG = "Clash/config/ACL4SSR_Online_Mini.ini"
POLICIES = {
    "🎯 全球直连": "DIRECT",
    "🛑 全球拦截": "REJECT",
    "🚀 节点选择": "Proxy",
    "🐟 漏网之鱼": "Proxy",
}
RULE_TYPES = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6",
    "PROCESS-NAME", "URL-REGEX",
}


def fetch(url: str) -> str:
    headers = {"User-Agent": "ProxyRules monthly builder"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8-sig")


def read_rules(text: str, source: str) -> list[str]:
    rules = []
    for number, raw in enumerate(text.splitlines(), 1):
        rule = raw.strip()
        if not rule or rule.startswith("#"):
            continue
        parts = rule.split(",")
        if parts[0] not in RULE_TYPES or len(parts) < 2 or not parts[1].strip():
            raise ValueError(f"{source}:{number}: invalid rule: {rule}")
        rules.append(rule)
    if not rules:
        raise ValueError(f"{source}: empty ruleset")
    return rules


def read_custom_rules(text: str, source: str) -> list[tuple[str, str]]:
    rules = []
    for number, raw in enumerate(text.splitlines(), 1):
        rule = raw.strip()
        if not rule or rule.startswith("#"):
            continue
        parts = rule.split(",")
        if (parts[0] not in RULE_TYPES or len(parts) not in (3, 4)
                or not parts[1].strip() or parts[2] not in ("DIRECT", "REJECT", "Proxy")
                or (len(parts) == 4 and (parts[3] != "no-resolve" or parts[0] not in ("IP-CIDR", "IP-CIDR6")))):
            raise ValueError(f"{source}:{number}: invalid custom rule: {rule}")
        rules.append((rule, parts[2]))
    return rules


def with_policy(rule: str, policy: str) -> str:
    parts = rule.split(",", 2)
    return ",".join(parts[:2] + [policy] + parts[2:])


def singbox_rule(rule: str, policy: str) -> dict | None:
    kind, value, *_ = rule.split(",")
    field = {
        "DOMAIN": "domain",
        "DOMAIN-SUFFIX": "domain_suffix",
        "DOMAIN-KEYWORD": "domain_keyword",
        "IP-CIDR": "ip_cidr",
        "IP-CIDR6": "ip_cidr",
        "PROCESS-NAME": "process_name",
    }.get(kind)
    if field is None:  # URL-REGEX has no sing-box route rule equivalent.
        return None
    return {field: [value], "outbound": {
        "DIRECT": "direct", "REJECT": "block", "Proxy": "节点选择",
    }[policy]}


def pack_singbox_rules(rules: list[dict]) -> list[dict]:
    """Merge adjacent rules with the same matcher and outbound, preserving order."""
    packed = []
    for rule in rules:
        fields = [key for key in rule if key not in ("outbound", "action")]
        if (packed and len(fields) == 1 and isinstance(rule[fields[0]], list)
                and packed[-1].get("outbound") == rule.get("outbound")
                and packed[-1].get("action") == rule.get("action")
                and set(packed[-1]) == set(rule)):
            packed[-1][fields[0]].extend(rule[fields[0]])
        else:
            packed.append({key: value.copy() if isinstance(value, list) else value
                           for key, value in rule.items()})
    return packed


def build() -> dict[Path, str]:
    personal_path = ROOT / "Rules/Personal.list"
    personal = read_rules(personal_path.read_text(encoding="utf-8"), str(personal_path))
    custom_path = ROOT / "Rules/Custom.list"
    custom = read_custom_rules(custom_path.read_text(encoding="utf-8"), str(custom_path))
    revision = json.loads(fetch(ACL_API))["sha"]
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("invalid ACL4SSR revision")
    config = fetch(f"{ACL_RAW}/{revision}/{CONFIG}")

    clash_rules = []
    surge_rules = []
    surfboard_rules = []
    singbox_rules = []
    shadow_rules = [f"# ACL4SSR Online Mini {revision[:12]}"]
    source_count = 0
    personal_inserted = False
    for line in config.splitlines():
        if not line.startswith("ruleset="):
            continue
        group, source = line[len("ruleset="):].split(",", 1)
        if group not in POLICIES:
            raise ValueError(f"unexpected upstream group: {group}")
        policy = POLICIES[group]
        if source.startswith("[]"):
            inline = source[2:]
            if inline == "GEOIP,CN" and policy == "DIRECT":
                clash_rules.append("GEOIP,CN,DIRECT")
                surge_rules.append("GEOIP,CN,DIRECT,no-resolve")
                surfboard_rules.append("GEOIP,CN,DIRECT,no-resolve")
                singbox_rules.append({"rule_set": ["geoip-cn"], "outbound": "direct"})
                shadow_rules.append("GEOIP,CN,DIRECT,no-resolve")
            elif inline == "FINAL" and policy == "Proxy":
                clash_rules.append("MATCH,Proxy")
                surge_rules.append("FINAL,Proxy")
                surfboard_rules.append("FINAL,Proxy")
                shadow_rules.append("FINAL,PROXY")
            else:
                raise ValueError(f"unexpected inline rule: {line}")
            continue
        prefix = f"{ACL_RAW}/master/Clash/"
        if not source.startswith(prefix):
            raise ValueError(f"unexpected upstream URL: {source}")
        relative = source.removeprefix(prefix)
        if not relative.endswith(".list") or ".." in Path(relative).parts:
            raise ValueError(f"unsafe upstream path: {relative}")
        source_rules = read_rules(fetch(f"{ACL_RAW}/{revision}/Clash/{relative}"), relative)
        for rule in source_rules:
            transformed = with_policy(rule, policy)
            # Clash does not support Surge's URL-REGEX rule type.
            if not rule.startswith("URL-REGEX,"):
                clash_rules.append(transformed)
            if not rule.startswith("URL-REGEX,"):
                surfboard_rules.append(transformed)
            surge_rules.append(transformed)
            shadow_rules.append(transformed.replace(",Proxy", ",PROXY"))
            converted = singbox_rule(rule, policy)
            if converted is not None:
                singbox_rules.append(converted)
        if relative == "BanProgramAD.list":
            for rule, custom_policy in custom:
                if not rule.startswith("URL-REGEX,"):
                    clash_rules.append(rule)
                    surfboard_rules.append(rule)
                surge_rules.append(rule)
                shadow_rules.append(rule.replace(",Proxy", ",PROXY"))
                converted = singbox_rule(rule, custom_policy)
                if converted is not None:
                    singbox_rules.append(converted)
            shadow_rules.extend([
                "# Personal direct rules follow advertisement blocking",
                "RULE-SET,https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list,DIRECT",
            ])
            personal_inserted = True
        source_count += 1

    if source_count < 8 or not personal_inserted or clash_rules[-1] != "MATCH,Proxy":
        raise ValueError("ACL4SSR configuration is incomplete")
    if not any(x.endswith(",REJECT") for x in clash_rules):
        raise ValueError("ACL4SSR configuration has no rejection rules")

    clash_base = (ROOT / "templates/xboard.clash.base.yaml").read_text(encoding="utf-8")
    surge_base = (ROOT / "templates/xboard.surge.base.conf").read_text(encoding="utf-8")
    surfboard_base = (ROOT / "templates/xboard.surfboard.base.conf").read_text(encoding="utf-8")
    singbox = json.loads((ROOT / "templates/xboard.singbox.base.json").read_text(encoding="utf-8"))
    singbox["route"]["rules"].extend(pack_singbox_rules(singbox_rules))
    singbox["route"]["final"] = "节点选择"
    shadow_base = (ROOT / "templates/shadowrocket.base.ini").read_text(encoding="utf-8")
    if shadow_base.count("{{RULES}}") != 1:
        raise ValueError("Shadowrocket base must contain one {{RULES}} marker")
    clash = clash_base + "\n".join("  - " + json.dumps(rule, ensure_ascii=False) for rule in clash_rules) + "\n"
    surge = surge_base + "\n".join(surge_rules) + "\n"
    surfboard = surfboard_base + "\n".join(surfboard_rules) + "\n"
    shadow = shadow_base.replace("{{RULES}}", "\n".join(shadow_rules))
    personal_clash = "payload:\n" + "\n".join(
        "  - " + json.dumps(rule, ensure_ascii=False) for rule in personal
    ) + "\n"
    return {
        ROOT / "Upstream/ACL4SSR-REVISION": revision + "\n",
        ROOT / "XBoard/clash.yaml": clash,
        ROOT / "XBoard/singbox.json": json.dumps(singbox, ensure_ascii=False, indent=2) + "\n",
        ROOT / "XBoard/stash.yaml": clash,
        ROOT / "XBoard/surge.conf": surge,
        ROOT / "XBoard/surfboard.conf": surfboard,
        ROOT / "Shadowrocket/nodnsleak-pk.ini": shadow,
        ROOT / "Rules/Personal.clash.yaml": personal_clash,
    }


def main() -> None:
    outputs = build()  # Validate every download before replacing any output.
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print("Generated templates from ACL4SSR revision", outputs[ROOT / "Upstream/ACL4SSR-REVISION"].strip())


if __name__ == "__main__":
    main()
