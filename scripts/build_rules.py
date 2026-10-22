#!/usr/bin/env python3
"""Build XBoard templates and public rule links from one ACL4SSR revision."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ACL_RAW = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR"
ACL_API = "https://api.github.com/repos/ACL4SSR/ACL4SSR/commits/master"
CONFIG = "Clash/config/ACL4SSR_Online_Full.ini"
SOURCE_PROXY_GROUP = "🚀 节点选择"
PROXY_GROUP = "🚀 默认代理"
SOURCE_AUTO_GROUP = "♻️ 自动选择"
AUTO_GROUP = "♻️ 自动优选"
MANUAL_GROUP = "🚀 手动选择"
NO_NODES_PATTERN = "~(?!)~u"
URL_TEST_INTERVAL = 10 * 60
URL_TEST_URL = "https://cp.cloudflare.com/generate_204"
REGION_FLAGS = {
    "🇭🇰 香港地区": "🇭🇰",
    "🇯🇵 日本地区": "🇯🇵",
    "🇺🇸 美国地区": "🇺🇸|🇺🇲",
    # The display marker is kept separate from node matching. Do not include
    # the unsupported Taiwan flag emoji in generated match expressions.
    "🇨🇳 台湾地区": "",
    "🇸🇬 新加坡地区": "🇸🇬",
    "🇰🇷 韩国地区": "🇰🇷",
}
REGION_GROUPS = (
    "🇭🇰 香港地区", "🇨🇳 台湾地区", "🇸🇬 新加坡地区",
    "🇯🇵 日本地区", "🇺🇸 美国地区", "🇰🇷 韩国地区",
)
DISPLAY_FIRST = (PROXY_GROUP, AUTO_GROUP, MANUAL_GROUP, *REGION_GROUPS)
DIRECT_GROUP = "🎯 全球直连"
REJECT_GROUP = "🛑 全球拦截"
FINAL_GROUP = "🐟 其他流量"
APP_DEFAULTS = {
    "📲 电报消息": PROXY_GROUP,
    "💬 Ai平台": "🇸🇬 新加坡地区",
    "📹 油管视频": "🇺🇸 美国地区",
    "🎥 奈飞视频": "🇺🇸 美国地区",
    "📺 巴哈姆特": "🇨🇳 台湾地区",
    "📺 哔哩哔哩": "DIRECT",
    "🌍 国外媒体": PROXY_GROUP,
    "📢 谷歌FCM": "DIRECT",
    "Ⓜ️ 微软Bing": "DIRECT",
    "Ⓜ️ 微软云盘": "DIRECT",
    "Ⓜ️ 微软服务": "DIRECT",
    "🍎 苹果服务": "DIRECT",
    "🎮 游戏平台": "DIRECT",
}
BLOCK_GROUPS = ("🛑 广告拦截", "🍃 应用净化")
REMOVED_GROUP = "🎥 奈飞节点"
FIXED_DIRECT_GROUPS = {"🌏 国内媒体", "🎶 网易音乐"}
HIDDEN_GROUPS = {DIRECT_GROUP, REJECT_GROUP, *FIXED_DIRECT_GROUPS}
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


def read_rules(text: str, source: str, *, allow_empty: bool = False) -> list[str]:
    rules = []
    for number, raw in enumerate(text.splitlines(), 1):
        rule = raw.strip()
        if not rule or rule.startswith("#"):
            continue
        parts = rule.split(",")
        if parts[0] not in RULE_TYPES or len(parts) < 2 or not parts[1].strip():
            raise ValueError(f"{source}:{number}: invalid rule: {rule}")
        rules.append(rule)
    if not rules and not allow_empty:
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
        name = rename_group(name)
        items = ["[]" + rename_group(item[2:]) if item.startswith("[]") else item
                 for item in items]
        if not name or name in {group["name"] for group in groups}:
            raise ValueError(f"invalid upstream proxy group: {line}")
        if kind == "select":
            if not items or any(not item for item in items):
                raise ValueError(f"unsupported upstream proxy group: {line}")
            groups.append({"name": name, "type": kind, "items": items})
        elif kind == "url-test":
            if len(items) != 3 or not items[0] or not items[1].startswith("http"):
                raise ValueError(f"unsupported upstream proxy group: {line}")
            timing = items[2].split(",")
            if len(timing) != 3 or not timing[0].isdigit() or timing[1] or not timing[2].isdigit():
                raise ValueError(f"unsupported upstream proxy group: {line}")
            groups.append({"name": name, "type": kind, "items": items[:2],
                           "interval": int(timing[0]), "tolerance": int(timing[2])})
        else:
            raise ValueError(f"unsupported upstream proxy group: {line}")
    names = {group["name"] for group in groups}
    if not {PROXY_GROUP, MANUAL_GROUP, DIRECT_GROUP, FINAL_GROUP}.issubset(names):
        raise ValueError("upstream proxy groups are incomplete")
    for group in groups:
        for item in group["items"]:
            if item.startswith("[]") and item[2:] not in names | {"DIRECT", "REJECT"}:
                raise ValueError(f"unknown upstream proxy group reference: {item}")
    return arrange_proxy_groups(groups)


def arrange_proxy_groups(groups: list[dict]) -> list[dict]:
    """Keep upstream rules, but give each visible group an explicit purpose."""
    known = set(DISPLAY_FIRST) | set(APP_DEFAULTS) | set(BLOCK_GROUPS) | HIDDEN_GROUPS | {FINAL_GROUP, REMOVED_GROUP}
    names = {group["name"] for group in groups}
    missing = known - names - {REJECT_GROUP}
    if names - known or missing:
        raise ValueError(f"update group mapping: added={sorted(names - known)}, missing={sorted(missing)}")
    result = []
    for source in groups:
        group = {**source, "items": source["items"].copy()}
        name = group["name"]
        if name == REMOVED_GROUP:
            continue
        if name == PROXY_GROUP:
            group["items"] = ["[]" + item for item in (AUTO_GROUP, MANUAL_GROUP, *REGION_GROUPS, "DIRECT")]
        elif name in APP_DEFAULTS:
            default = APP_DEFAULTS[name]
            options = [PROXY_GROUP, *REGION_GROUPS, "DIRECT"]
            # Clients without a selector default field use the first member.
            options.remove(default)
            options.insert(0, default)
            group.update(type="select", items=["[]" + item for item in options] + [".*"], default=default)
        elif name in FIXED_DIRECT_GROUPS:
            group["items"] = ["[]DIRECT"]
        elif name in BLOCK_GROUPS:
            group["items"] = ["[]REJECT", "[]DIRECT"]
        elif name == FINAL_GROUP:
            group["items"] = ["[]" + PROXY_GROUP, "[]DIRECT"]
        if group["type"] == "url-test":
            group["interval"] = URL_TEST_INTERVAL
            group["items"][1] = URL_TEST_URL
        result.append(group)
    return result


def rename_group(name: str) -> str:
    return {
        SOURCE_PROXY_GROUP: PROXY_GROUP,
        SOURCE_AUTO_GROUP: AUTO_GROUP,
        "🚀 模式选择": PROXY_GROUP,
        "🚀 默认出口": PROXY_GROUP,
        "🇸🇬 狮城节点": "🇸🇬 新加坡地区",
        '🇭🇰 香港节点': '🇭🇰 香港地区',
        '🇨🇳 台湾节点': '🇨🇳 台湾地区',
        '🇸🇬 新加坡节点': '🇸🇬 新加坡地区',
        '🇯🇵 日本节点': '🇯🇵 日本地区',
        '🇺🇲 美国节点': '🇺🇸 美国地区',
        '🇰🇷 韩国节点': '🇰🇷 韩国地区',
        "♻️ 延迟优选": AUTO_GROUP,
        "🚀 手动切换": MANUAL_GROUP,
        "🐟 漏网之鱼": FINAL_GROUP,
    }.get(name, name)


def display_order(groups: list[dict]) -> list[dict]:
    """Put frequently used groups first without changing their members."""
    first = {name: index for index, name in enumerate(DISPLAY_FIRST)}
    apps = {name: index for index, name in enumerate(APP_DEFAULTS)}
    blocks = {name: index for index, name in enumerate(BLOCK_GROUPS)}

    def order(group: dict) -> tuple[int, int]:
        name = group["name"]
        if name in first:
            return 0, first[name]
        if name in apps:
            return 1, apps[name]
        if name in blocks:
            return 2, blocks[name]
        return 3, 0

    return sorted(groups, key=order)


def policy_name(name: str, client: str = "clash") -> str:
    name = rename_group(name)
    if name in {DIRECT_GROUP, "DIRECT", *FIXED_DIRECT_GROUPS}:
        return "direct" if client == "singbox" else "DIRECT"
    if name in (REJECT_GROUP, "REJECT"):
        return "block" if client == "singbox" else "REJECT"
    return name


def shadow_policy(name: str, groups: dict[str, dict], seen: frozenset[str] = frozenset()) -> str:
    if name in {DIRECT_GROUP, "DIRECT", *FIXED_DIRECT_GROUPS}:
        return "DIRECT"
    if name == REJECT_GROUP or name == "REJECT":
        return "REJECT"
    if name in seen:
        raise ValueError(f"cyclic default proxy group: {name}")
    group = groups[name]
    first = group["items"][0]
    if not first.startswith("[]"):
        return "PROXY"
    return shadow_policy(first[2:], groups, seen | {name})


def node_expression(group: dict) -> str | None:
    patterns = [group["items"][0]] if group["type"] == "url-test" else [item for item in group["items"] if not item.startswith("[]")]
    if not patterns:
        return None
    expression = "|".join(f"(?:{pattern})" for pattern in patterns)
    if group["name"] in REGION_FLAGS and REGION_FLAGS[group["name"]]:
        expression += "|(?:" + REGION_FLAGS[group["name"]] + ")"
    if "~" in expression:
        raise ValueError(f"unsupported XBoard regex delimiter in {group['name']}")
    return expression


def clash_proxy_groups(groups: list[dict]) -> list[dict]:
    result = []
    for group in groups:
        if group["name"] in HIDDEN_GROUPS:
            continue
        members = [policy_name(item[2:]) for item in group["items"] if item.startswith("[]")]
        expression = node_expression(group)
        if expression is not None:
            # XBoard expands regex entries in proxies against the user's nodes.
            # Its subscription handler does not apply Mihomo's filter field.
            if expression != "(?:.*)":
                keep_empty_group = not members
                members.append(f"~{expression}~u")
                # Keep the group present without allowing a different region
                # to win its latency test. REJECT never provides connectivity.
                if keep_empty_group:
                    members.append("REJECT")
        else:
            # XBoard otherwise appends every subscription node to this group.
            members.append(NO_NODES_PATTERN)
        entry = {"name": group["name"], "type": group["type"], "proxies": members}
        if group["type"] == "url-test":
            entry.update({"url": group["items"][1], "interval": group["interval"],
                          "tolerance": group["tolerance"]})
        result.append(entry)
    return result


def surge_proxy_groups(groups: list[dict]) -> str:
    lines = []
    for group in groups:
        if group["name"] in HIDDEN_GROUPS:
            continue
        if group["type"] == "select":
            members = [policy_name(item[2:]) if item.startswith("[]") else "$proxy_group"
                       for item in group["items"]]
        else:
            expression = node_expression(group)
            if expression == "(?:.*)":
                members = ["$proxy_group"]
            else:
                # Regex filtering applies to dynamically included proxies,
                # not to explicitly listed policies.
                members = ["include-all-proxies=true",
                           'policy-regex-filter=".*(?:' + expression + ').*"', "REJECT"]
            members += [f"url={group['items'][1]}",
                       f"interval={group['interval']}", f"tolerance={group['tolerance']}"]
        lines.append(f"{group['name']} = {group['type']}, " + ", ".join(members))
    return "\n".join(lines)


def singbox_proxy_groups(groups: list[dict]) -> list[dict]:
    outbounds = []
    for group in groups:
        if group["name"] in HIDDEN_GROUPS:
            continue
        members = [policy_name(item[2:], "singbox")
                   for item in group["items"] if item.startswith("[]")]
        outbound = {"type": "selector" if group["type"] == "select" else "urltest",
                    "tag": group["name"], "outbounds": members}
        expression = node_expression(group)
        if expression is None:
            outbound["include"] = NO_NODES_PATTERN
        elif expression != "(?:.*)":
            outbound["include"] = f"~{expression}~u"
            outbound["fallback"] = "block"
        if "default" in group:
            outbound["default"] = policy_name(group["default"], "singbox")
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


def clash_dns_policies(rules: list[str]) -> tuple[dict, dict]:
    """Bind the ordered domain-rule projection to its own outbound group.

    Separate contiguous policy runs preserve overlapping rules and keywords;
    grouping all rules by policy would change first-match precedence.
    """
    runs: list[tuple[str, list[str]]] = []
    for rule in rules:
        parts = rule.split(",")
        if parts[0] not in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"):
            continue
        policy = parts[2]
        matcher = ",".join(parts[:2])
        if runs and runs[-1][0] == policy:
            runs[-1][1].append(matcher)
        else:
            runs.append((policy, [matcher]))
    policies, providers = {}, {}
    for index, (policy, matchers) in enumerate(runs):
        name = f"dns-policy-{index:03d}"
        providers[name] = {"type": "inline", "behavior": "classical", "payload": matchers}
        policies["rule-set:" + name] = (
            ["https://1.12.12.12/dns-query#DIRECT", "https://120.53.53.53/dns-query#DIRECT"] if policy == "DIRECT" else
            [f"https://1.1.1.1/dns-query#{policy}", f"https://8.8.8.8/dns-query#{policy}"]
        )
    return policies, providers


def singbox_dns_rules(rules: list[dict], servers: dict[str, str]) -> list[dict]:
    """Project every domain rule in order, including proxy exceptions."""
    dns_rules = []
    for rule in rules:
        matcher = {key: value for key, value in rule.items()
                   if key in ("domain", "domain_suffix", "domain_keyword")}
        if not matcher:
            continue
        outbound = rule.get("outbound")
        if outbound == "block":
            dns_rules.append({**matcher, "action": "reject"})
        else:
            dns_rules.append({**matcher, "server": servers[outbound]})
    packed = []
    for rule in dns_rules:
        fields = [key for key in rule if key not in ("server", "action")]
        if (packed and len(fields) == 1 and packed[-1].get("server") == rule.get("server")
                and packed[-1].get("action") == rule.get("action")
                and set(packed[-1]) == set(rule)):
            packed[-1][fields[0]].extend(rule[fields[0]])
        else:
            packed.append({key: value.copy() if isinstance(value, list) else value
                           for key, value in rule.items()})
    return packed


def surge_dns_hosts(rules: list[str]) -> list[str]:
    """Map explicit direct domains and earlier proxy exceptions to DoH."""
    domain_rules = []
    for rule in rules:
        kind, value, *rest = rule.split(",")
        if kind in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD") and rest:
            domain_rules.append((kind, value.lower(), rest[0]))

    direct_suffixes = [value for kind, value, policy in domain_rules
                       if kind == "DOMAIN-SUFFIX" and policy == "DIRECT"]

    def policy_for(domain: str) -> str | None:
        for kind, value, policy in domain_rules:
            if (kind == "DOMAIN" and domain == value
                    or kind == "DOMAIN-SUFFIX" and (domain == value or domain.endswith("." + value))
                    or kind == "DOMAIN-KEYWORD" and value in domain):
                return policy
        return None

    hosts = []
    seen = {"dns.cloudflare.com", "dns.google", "doh.pub"}
    for kind, value, policy in domain_rules:
        if kind == "DOMAIN-KEYWORD":
            continue
        if policy == "DIRECT":
            server = "https://1.12.12.12/dns-query"
        elif (policy not in ("REJECT", "🛑 广告拦截", "🍃 应用净化")
              and any(
                  value == suffix or value.endswith("." + suffix)
                  for suffix in direct_suffixes)):
            # These proxy rules precede broader direct suffixes such as .cn.
            server = "https://1.1.1.1/dns-query"
        else:
            continue
        if policy == "DIRECT":
            patterns = ([value] if policy_for(value) == "DIRECT" else [])
            if kind == "DOMAIN-SUFFIX" and policy_for("dns-probe." + value) == "DIRECT":
                patterns.append("*." + value)
        else:
            patterns = [value] if kind == "DOMAIN" else [value, "*." + value]
        for pattern in patterns:
            if pattern not in seen:
                hosts.append(f"{pattern} = server:{server}")
                seen.add(pattern)
    return hosts


def read_personal_routes(text: str, source: str) -> list[str]:
    rules = read_rules(text, source)
    for rule in rules:
        parts = rule.split(",")
        if (len(parts) not in (3, 4) or not parts[2].strip()
                or parts[2] != parts[2].strip()
                or (len(parts) == 4 and (parts[3] != "no-resolve"
                    or parts[0] not in ("IP-CIDR", "IP-CIDR6")))):
            raise ValueError(f"{source}: invalid personal route: {rule}")
    return rules


def build_personal() -> dict[Path, str]:
    direct_path = ROOT / "Rules/Personal.list"
    direct = read_rules(direct_path.read_text(encoding="utf-8"), str(direct_path), allow_empty=True)
    routes_path = ROOT / "Rules/Personal.routes.list"
    routes = read_personal_routes(routes_path.read_text(encoding="utf-8"), str(routes_path))
    rules = routes + [with_policy(rule, "DIRECT") for rule in direct]
    return {ROOT / "Rules/Personal.clash.yaml": "rules:\n" + "\n".join(
        "  - " + json.dumps(rule, ensure_ascii=False) for rule in rules
    ) + "\n"}


def build(revision: str | None = None) -> dict[Path, str]:
    personal_outputs = build_personal()
    custom_path = ROOT / "Rules/Custom.list"
    custom = read_custom_rules(custom_path.read_text(encoding="utf-8"), str(custom_path))
    revision = revision or json.loads(fetch(ACL_API))["sha"]
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("invalid ACL4SSR revision")
    config = fetch(f"{ACL_RAW}/{revision}/{CONFIG}")
    groups = display_order(read_proxy_groups(config))
    group_names = {group["name"] for group in groups}
    group_map = {group["name"]: group for group in groups}
    shadow_policies = {name: shadow_policy(name, group_map) for name in group_names}

    clash_rules = []
    surge_rules = []
    surfboard_rules = []
    singbox_rules = []
    shadow_rules = [f"# ACL4SSR Online Full {revision[:12]}"]
    source_count = 0
    personal_inserted = False
    for line in config.splitlines():
        if not line.startswith("ruleset="):
            continue
        group, source = line[len("ruleset="):].split(",", 1)
        group = rename_group(group)
        if group not in group_names:
            raise ValueError(f"unexpected upstream group: {group}")
        policy = policy_name(group)
        if source.startswith("[]"):
            inline = source[2:]
            if inline == "GEOIP,CN" and group == DIRECT_GROUP:
                clash_rules.append(f"GEOIP,CN,{policy}")
                surge_rules.append(f"GEOIP,CN,{policy},no-resolve")
                surfboard_rules.append(f"GEOIP,CN,{policy},no-resolve")
                singbox_rules.append({"rule_set": ["geoip-cn"], "outbound": "direct"})
                shadow_rules.append("GEOIP,CN,DIRECT,no-resolve")
            elif inline == "FINAL" and group == FINAL_GROUP:
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
            shadow_rules.append(with_policy(rule, shadow_policies[group]))
            converted = singbox_rule(rule, policy_name(group, "singbox"))
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
    if not any(x.endswith(",🛑 广告拦截") for x in clash_rules):
        raise ValueError("ACL4SSR configuration has no rejection rules")

    clash_base = (ROOT / "templates/xboard.clash.base.yaml").read_text(encoding="utf-8")
    clashmeta_tun = (ROOT / "templates/xboard.clashmeta.tun.yaml").read_text(encoding="utf-8")
    stash_base = (ROOT / "templates/xboard.stash.base.yaml").read_text(encoding="utf-8")
    surge_base = (ROOT / "templates/xboard.surge.base.conf").read_text(encoding="utf-8")
    surfboard_base = (ROOT / "templates/xboard.surfboard.base.conf").read_text(encoding="utf-8")
    for name, template in (("Clash", clash_base), ("Stash", stash_base), ("Surge", surge_base),
                           ("Surfboard", surfboard_base)):
        if template.count("{{PROXY_GROUPS}}") != 1:
            raise ValueError(f"{name} base must contain one {{PROXY_GROUPS}} marker")
    if surge_base.count("{{DNS_HOSTS}}") != 1:
        raise ValueError("Surge base must contain one {DNS_HOSTS} marker")
    for marker in ("{{DNS_POLICIES}}", "{{DNS_RULE_PROVIDERS}}"):
        if clash_base.count(marker) != 1:
            raise ValueError(f"Clash base must contain one {marker} marker")
    singbox = json.loads((ROOT / "templates/xboard.singbox.base.json").read_text(encoding="utf-8"))
    packed_singbox_rules = pack_singbox_rules(singbox_rules)
    dns_server_tags = {"direct": "local", FINAL_GROUP: "remote"}
    needed_dns_outbounds = {PROXY_GROUP} | {
        rule["outbound"] for rule in packed_singbox_rules
        if any(field in rule for field in ("domain", "domain_suffix", "domain_keyword"))
    }
    for index, group in enumerate(groups):
        name = group["name"]
        if name in HIDDEN_GROUPS or name == FINAL_GROUP or name not in needed_dns_outbounds:
            continue
        tag = f"dns-outbound-{index:03d}"
        dns_server_tags[name] = tag
        singbox["dns"]["servers"].append({
            "tag": tag, "type": "https", "server": "1.1.1.1", "detour": name,
        })
    singbox["dns"]["rules"][1]["server"] = dns_server_tags[PROXY_GROUP]
    singbox["dns"]["rules"].extend(singbox_dns_rules(packed_singbox_rules, dns_server_tags))
    singbox["route"]["rules"].extend(packed_singbox_rules)
    singbox["outbounds"] = singbox_proxy_groups(groups) + [
        outbound for outbound in singbox["outbounds"] if outbound["tag"] in ("direct", "block")]
    singbox["route"]["final"] = FINAL_GROUP
    shadow_base = (ROOT / "templates/shadowrocket.base.ini").read_text(encoding="utf-8")
    if shadow_base.count("{{RULES}}") != 1:
        raise ValueError("Shadowrocket base must contain one {{RULES}} marker")
    dns_policies, dns_providers = clash_dns_policies(clash_rules)
    clash_base = clash_base.replace("{{DNS_POLICIES}}", "\n".join(
        "    " + json.dumps(key, ensure_ascii=False) + ": " + json.dumps(value, ensure_ascii=False)
        for key, value in dns_policies.items()))
    clash_base = clash_base.replace("{{DNS_RULE_PROVIDERS}}", "\n".join(
        "  " + json.dumps(key) + ": " + json.dumps(value, ensure_ascii=False)
        for key, value in dns_providers.items()))
    clash = clash_base.replace("{{PROXY_GROUPS}}", "\n".join(
        "  - " + json.dumps(group, ensure_ascii=False) for group in clash_proxy_groups(groups))) + "\n".join(
        "  - " + json.dumps(rule, ensure_ascii=False) for rule in clash_rules) + "\n"
    clashmeta = clashmeta_tun + clash
    stash = stash_base.replace("{{PROXY_GROUPS}}", "\n".join(
        "  - " + json.dumps(group, ensure_ascii=False) for group in clash_proxy_groups(groups))) + "\n".join(
        "  - " + json.dumps(rule, ensure_ascii=False) for rule in [
            f"IP-CIDR,1.1.1.1/32,{AUTO_GROUP}",
            f"IP-CIDR,8.8.8.8/32,{AUTO_GROUP}",
            "IP-CIDR,1.12.12.12/32,DIRECT",
            "IP-CIDR,120.53.53.53/32,DIRECT",
        ] + clash_rules) + "\n"
    surge = (surge_base.replace("{{PROXY_GROUPS}}", surge_proxy_groups(groups))
             .replace("{{DNS_HOSTS}}", "\n".join(surge_dns_hosts(surge_rules)))
             + "\n".join(surge_rules) + "\n")
    surfboard = surfboard_base.replace("{{PROXY_GROUPS}}", surge_proxy_groups(groups)) + "\n".join(surfboard_rules) + "\n"
    shadow = shadow_base.replace("{{RULES}}", "\n".join(shadow_rules))
    return {
        ROOT / "Upstream/ACL4SSR-REVISION": revision + "\n",
        ROOT / "XBoard/clash.yaml": clash,
        ROOT / "XBoard/clashmeta.yaml": clashmeta,
        ROOT / "XBoard/singbox.json": json.dumps(singbox, ensure_ascii=False, indent=2) + "\n",
        ROOT / "XBoard/stash.yaml": stash,
        ROOT / "XBoard/surge.conf": surge,
        ROOT / "XBoard/surfboard.conf": surfboard,
        ROOT / "Shadowrocket/nodnsleak-pk.ini": shadow,
        **personal_outputs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", help="Rebuild a specific ACL4SSR commit instead of updating rules")
    parser.add_argument("--personal-only", action="store_true", help="Generate personal rule sets without downloading upstream rules")
    args = parser.parse_args()
    if args.personal_only and args.revision:
        parser.error("--personal-only cannot be combined with --revision")
    outputs = build_personal() if args.personal_only else build(args.revision)
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    if args.personal_only:
        print("Generated personal Clash rule sets")
    else:
        print("Generated templates from ACL4SSR revision", outputs[ROOT / "Upstream/ACL4SSR-REVISION"].strip())


if __name__ == "__main__":
    main()
