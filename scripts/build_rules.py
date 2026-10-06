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
PROXY_GROUP = "🚀 节点选择"
DIRECT_GROUP = "🎯 全球直连"
REJECT_GROUP = "🛑 全球拦截"
FINAL_GROUP = "🐟 漏网之鱼"
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
        "DIRECT": "direct", "REJECT": "block", "Proxy": PROXY_GROUP,
    }.get(policy, policy)}


def read_proxy_groups(config: str) -> list[dict]:
    groups = []
    for line in config.splitlines():
        if not line.startswith("custom_proxy_group="):
            continue
        fields = line.removeprefix("custom_proxy_group=").split("`")
        name, kind, *items = fields
        if not name or name in {group["name"] for group in groups}:
            raise ValueError(f"invalid upstream proxy group: {line}")
        if kind == "select":
            if not items or any(not item or (not item.startswith("[]") and item != ".*") for item in items):
                raise ValueError(f"unsupported upstream proxy group: {line}")
            groups.append({"name": name, "type": kind, "items": items})
        elif kind == "url-test":
            if len(items) != 3 or items[0] != ".*" or not items[1].startswith("http"):
                raise ValueError(f"unsupported upstream proxy group: {line}")
            timing = items[2].split(",")
            if len(timing) != 3 or not timing[0].isdigit() or timing[1] or not timing[2].isdigit():
                raise ValueError(f"unsupported upstream proxy group: {line}")
            groups.append({"name": name, "type": kind, "items": items[:2],
                           "interval": int(timing[0]), "tolerance": int(timing[2])})
        else:
            raise ValueError(f"unsupported upstream proxy group: {line}")
    names = {group["name"] for group in groups}
    if not {PROXY_GROUP, DIRECT_GROUP, REJECT_GROUP, FINAL_GROUP}.issubset(names):
        raise ValueError("upstream proxy groups are incomplete")
    for group in groups:
        for item in group["items"]:
            if item.startswith("[]") and item[2:] not in names | {"DIRECT", "REJECT"}:
                raise ValueError(f"unknown upstream proxy group reference: {item}")
    return groups


def clash_proxy_groups(groups: list[dict]) -> list[dict]:
    result = []
    for group in groups:
        entry = {"name": group["name"], "type": group["type"],
                 "proxies": [item[2:] for item in group["items"] if item.startswith("[]")]}
        if ".*" in group["items"]:
            entry.update({"include-all": True, "filter": ".*"})
        if group["type"] == "url-test":
            entry.update({"url": group["items"][1], "interval": group["interval"],
                          "tolerance": group["tolerance"]})
        result.append(entry)
    return result


def surge_proxy_groups(groups: list[dict]) -> str:
    lines = []
    for group in groups:
        if group["type"] == "select":
            members = [item[2:] if item.startswith("[]") else "$proxy_group"
                       for item in group["items"]]
        else:
            members = ["$proxy_group", f"url={group['items'][1]}",
                       f"interval={group['interval']}", f"tolerance={group['tolerance']}"]
        lines.append(f"{group['name']} = {group['type']}, " + ", ".join(members))
    return "\n".join(lines)


def singbox_proxy_groups(groups: list[dict]) -> list[dict]:
    outbounds = []
    for group in groups:
        members = [{"DIRECT": "direct", "REJECT": "block"}.get(item[2:], item[2:])
                   for item in group["items"] if item.startswith("[]")]
        outbound = {"type": "selector" if group["type"] == "select" else "urltest",
                    "tag": group["name"], "outbounds": members}
        if group["type"] == "url-test":
            outbound["url"] = group["items"][1]
            outbound["interval"] = f"{group['interval']}s"
            outbound["tolerance"] = group["tolerance"]
        outbounds.append(outbound)
    return outbounds


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


def singbox_dns_rules(rules: list[dict]) -> list[dict]:
    """Mirror domain route policies in DNS server selection."""
    dns_rules = []
    proxy_dns_index = 0
    for rule in rules:
        matcher = {key: value for key, value in rule.items()
                   if key in ("domain", "domain_suffix", "domain_keyword")}
        if not matcher:
            continue
        outbound = rule.get("outbound")
        if outbound in ("direct", DIRECT_GROUP):
            server = "local"
        else:
            server = "remote" if proxy_dns_index % 2 == 0 else "remote-google"
            proxy_dns_index += 1
        dns_rules.append({**matcher, "server": server})
    packed = []
    for rule in dns_rules:
        fields = [key for key in rule if key != "server"]
        if (packed and len(fields) == 1 and packed[-1].get("server") == rule["server"]
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
    groups = read_proxy_groups(config)
    group_names = {group["name"] for group in groups}
    shadow_policies = {DIRECT_GROUP: "DIRECT", REJECT_GROUP: "REJECT",
                       PROXY_GROUP: "PROXY", FINAL_GROUP: "PROXY"}

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
        if group not in group_names:
            raise ValueError(f"unexpected upstream group: {group}")
        policy = group
        if source.startswith("[]"):
            inline = source[2:]
            if inline == "GEOIP,CN" and policy == DIRECT_GROUP:
                clash_rules.append(f"GEOIP,CN,{policy}")
                surge_rules.append(f"GEOIP,CN,{policy},no-resolve")
                surfboard_rules.append(f"GEOIP,CN,{policy},no-resolve")
                singbox_rules.append({"rule_set": ["geoip-cn"], "outbound": policy})
                shadow_rules.append("GEOIP,CN,DIRECT,no-resolve")
            elif inline == "FINAL" and policy == FINAL_GROUP:
                clash_rules.append(f"MATCH,{policy}")
                surge_rules.append(f"FINAL,{policy}")
                surfboard_rules.append(f"FINAL,{policy}")
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
            shadow_rules.append(with_policy(rule, shadow_policies[policy]))
            converted = singbox_rule(rule, policy)
            if converted is not None:
                singbox_rules.append(converted)
        if relative == "BanProgramAD.list":
            for rule, custom_policy in custom:
                if not rule.startswith("URL-REGEX,"):
                    clash_rules.append(rule.replace(",Proxy", f",{PROXY_GROUP}"))
                    surfboard_rules.append(rule.replace(",Proxy", f",{PROXY_GROUP}"))
                surge_rules.append(rule.replace(",Proxy", f",{PROXY_GROUP}"))
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

    if source_count < 8 or not personal_inserted or clash_rules[-1] != f"MATCH,{FINAL_GROUP}":
        raise ValueError("ACL4SSR configuration is incomplete")
    if not any(x.endswith(f",{REJECT_GROUP}") for x in clash_rules):
        raise ValueError("ACL4SSR configuration has no rejection rules")

    clash_base = (ROOT / "templates/xboard.clash.base.yaml").read_text(encoding="utf-8")
    clashmeta_tun = (ROOT / "templates/xboard.clashmeta.tun.yaml").read_text(encoding="utf-8")
    surge_base = (ROOT / "templates/xboard.surge.base.conf").read_text(encoding="utf-8")
    surfboard_base = (ROOT / "templates/xboard.surfboard.base.conf").read_text(encoding="utf-8")
    for name, template in (("Clash", clash_base), ("Surge", surge_base),
                           ("Surfboard", surfboard_base)):
        if template.count("{{PROXY_GROUPS}}") != 1:
            raise ValueError(f"{name} base must contain one {{PROXY_GROUPS}} marker")
    singbox = json.loads((ROOT / "templates/xboard.singbox.base.json").read_text(encoding="utf-8"))
    packed_singbox_rules = pack_singbox_rules(singbox_rules)
    singbox["dns"]["rules"].extend(singbox_dns_rules(packed_singbox_rules))
    singbox["route"]["rules"].extend(packed_singbox_rules)
    singbox["outbounds"] = singbox_proxy_groups(groups) + [
        outbound for outbound in singbox["outbounds"] if outbound["tag"] in ("direct", "block")]
    singbox["route"]["final"] = FINAL_GROUP
    shadow_base = (ROOT / "templates/shadowrocket.base.ini").read_text(encoding="utf-8")
    if shadow_base.count("{{RULES}}") != 1:
        raise ValueError("Shadowrocket base must contain one {{RULES}} marker")
    clash = clash_base.replace("{{PROXY_GROUPS}}", "\n".join(
        "  - " + json.dumps(group, ensure_ascii=False) for group in clash_proxy_groups(groups))) + "\n".join(
        "  - " + json.dumps(rule, ensure_ascii=False) for rule in clash_rules) + "\n"
    clashmeta = clashmeta_tun + clash
    surge = surge_base.replace("{{PROXY_GROUPS}}", surge_proxy_groups(groups)) + "\n".join(surge_rules) + "\n"
    surfboard = surfboard_base.replace("{{PROXY_GROUPS}}", surge_proxy_groups(groups)) + "\n".join(surfboard_rules) + "\n"
    shadow = shadow_base.replace("{{RULES}}", "\n".join(shadow_rules))
    personal_clash = "payload:\n" + "\n".join(
        "  - " + json.dumps(rule, ensure_ascii=False) for rule in personal
    ) + "\n"
    return {
        ROOT / "Upstream/ACL4SSR-REVISION": revision + "\n",
        ROOT / "XBoard/clash.yaml": clash,
        ROOT / "XBoard/clashmeta.yaml": clashmeta,
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
