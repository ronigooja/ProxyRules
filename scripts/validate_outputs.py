#!/usr/bin/env python3
"""Check generated client files before publishing any XBoard template."""

import json
import re
import sys
from fnmatch import fnmatchcase
from ipaddress import ip_address
from urllib.parse import urlsplit
from pathlib import Path

import yaml
sys.dont_write_bytecode = True
from build_rules import (APP_DEFAULTS, AUTO_GROUP, BLOCK_GROUPS, DIRECT_GROUP, DISPLAY_FIRST, FINAL_GROUP,
                         MANUAL_GROUP, REGION_GROUPS, REMOVED_GROUP,
                         PROXY_GROUP, SOURCE_AUTO_GROUP, SOURCE_PROXY_GROUP,
                         read_custom_rules, read_rules, read_personal_routes, with_policy,
                         singbox_rule, clash_dns_policies)


ROOT = Path(__file__).resolve().parents[1]
clash = yaml.safe_load((ROOT / "XBoard/clash.yaml").read_text(encoding="utf-8"))
clashmeta = yaml.safe_load((ROOT / "XBoard/clashmeta.yaml").read_text(encoding="utf-8"))
stash = yaml.safe_load((ROOT / "XBoard/stash.yaml").read_text(encoding="utf-8"))
singbox = json.loads((ROOT / "XBoard/singbox.json").read_text(encoding="utf-8"))
personal = yaml.safe_load((ROOT / "Rules/Personal.clash.yaml").read_text(encoding="utf-8"))
surge = (ROOT / "XBoard/surge.conf").read_text(encoding="utf-8")
surfboard = (ROOT / "XBoard/surfboard.conf").read_text(encoding="utf-8")
shadow = (ROOT / "Shadowrocket/nodnsleak-pk.ini").read_text(encoding="utf-8")
custom_path = ROOT / "Rules/Custom.list"
custom = read_custom_rules(custom_path.read_text(encoding="utf-8"), str(custom_path))
personal_list = (ROOT / "Rules/Personal.list").read_text(encoding="utf-8")
personal_rules = read_rules(personal_list, "Rules/Personal.list", allow_empty=True)
personal_routes = read_personal_routes((ROOT / "Rules/Personal.routes.list").read_text(encoding="utf-8"), "Rules/Personal.routes.list")

assert isinstance(clash.get("proxy-groups"), list)
group_names = [group["name"] for group in clash["proxy-groups"]]
assert group_names[:len(DISPLAY_FIRST)] == list(DISPLAY_FIRST)
assert group_names[-1] == FINAL_GROUP
assert set(group_names) >= {PROXY_GROUP, FINAL_GROUP}
assert DIRECT_GROUP not in group_names and "🛑 全球拦截" not in group_names
groups = {group["name"]: group for group in clash["proxy-groups"]}
assert "DIRECT" in groups[PROXY_GROUP]["proxies"]
assert groups[PROXY_GROUP]["proxies"][-1] == "~(?!)~u"
assert not re.search(groups[PROXY_GROUP]["proxies"][-1][1:-2], "Hong Kong 01")
auto_group = groups[PROXY_GROUP]["proxies"][0]
assert auto_group == AUTO_GROUP
assert groups[auto_group]["type"] == "url-test"
assert groups[auto_group]["proxies"] == []
assert groups[MANUAL_GROUP]["proxies"] == []
assert set(group_names) >= {"💬 Ai平台", "🎥 奈飞视频", "🇭🇰 香港地区"}
hong_kong = groups["🇭🇰 香港地区"]["proxies"]
assert hong_kong[0] == "REJECT"
assert len(hong_kong) == 2 and hong_kong[1].startswith("~") and hong_kong[1].endswith("~u")
assert re.search(hong_kong[1][1:-2], "Hong Kong 01")
assert re.search(hong_kong[1][1:-2], "🇭🇰 01")
assert not re.search(hong_kong[1][1:-2], "Japan 01")
assert REMOVED_GROUP not in groups
for name, default in APP_DEFAULTS.items():
    assert groups[name]["type"] == "select"
    assert groups[name]["proxies"][0] == default
    assert set(groups[name]["proxies"]) == {PROXY_GROUP, *REGION_GROUPS, "DIRECT"}
assert group_names[len(DISPLAY_FIRST):-3] == list(APP_DEFAULTS)
assert group_names[-3:-1] == list(BLOCK_GROUPS)
for name in (*BLOCK_GROUPS, FINAL_GROUP):
    assert groups[name]["proxies"][-1] == "~(?!)~u"
for group in groups.values():
    assert all(member in groups or member in {"DIRECT", "REJECT"} or member.startswith("~") for member in group["proxies"])

# Exercise the XBoard expansion behavior that originally injected nodes into
# reference-only groups. Unlabelled nodes must still be available in every app.
sample_nodes = ["Hong Kong 01", "🇭🇰 02", "Japan 01", "🇺🇸 01", "普通节点 01"]
expanded = {}
for name, group in groups.items():
    filters = [member for member in group["proxies"] if member.startswith("~")]
    refs = [member for member in group["proxies"] if not member.startswith("~")]
    nodes = [node for node in sample_nodes if not filters or any(
        re.search(pattern[1:-2], node) for pattern in filters)]
    expanded[name] = refs + nodes
for name in (PROXY_GROUP, *BLOCK_GROUPS, FINAL_GROUP):
    assert not set(expanded[name]) & set(sample_nodes)
for name, default in APP_DEFAULTS.items():
    assert expanded[name][0] == default
    assert set(sample_nodes) <= set(expanded[name])
assert set(expanded["🇭🇰 香港地区"]) == {"REJECT", "Hong Kong 01", "🇭🇰 02"}
assert MANUAL_GROUP not in expanded["🇭🇰 香港地区"]
assert all("include-all" not in group and "filter" not in group for group in groups.values())
assert groups[auto_group]["interval"] > 0
assert groups[auto_group]["tolerance"] >= 0
assert isinstance(clash.get("rules"), list) and len(clash["rules"]) > 1000
assert {key: value for key, value in stash.items() if key not in ("dns", "rules")} == {key: value for key, value in clash.items() if key not in ("dns", "rules", "rule-providers")}
assert stash["rules"][3:] == clash["rules"]
assert stash["rules"][:3] == [
    f"IP-CIDR,1.1.1.1/32,{AUTO_GROUP}",
    f"IP-CIDR,8.8.8.8/32,{AUTO_GROUP}",
    "IP-CIDR,223.5.5.5/32,DIRECT",
]
assert {key: value for key, value in clashmeta.items() if key != "tun"} == clash
assert "enable" not in clashmeta["tun"]
assert clashmeta["tun"]["auto-route"] is True
assert clashmeta["tun"]["auto-detect-interface"] is True
assert set(clashmeta["tun"]["dns-hijack"]) == {"any:53", "tcp://any:53"}
dns = clash["dns"]
assert dns == clashmeta["dns"]
assert all(server.startswith("https://") for key in ("default-nameserver", "proxy-server-nameserver", "direct-nameserver", "nameserver") for server in dns[key])
assert all("dns.alidns.com" in server or "223.5.5.5" in server for server in dns["direct-nameserver"] + dns["proxy-server-nameserver"])
assert all(server.endswith("#DIRECT") for server in dns["direct-nameserver"])
assert all(urlsplit(server).hostname in {"1.1.1.1", "8.8.8.8"}
           and urlsplit(server).fragment in group_names
           for server in dns["nameserver"])
assert dns["direct-nameserver-follow-policy"] is False
assert "fallback" not in dns
assert all(urlsplit(server).fragment == FINAL_GROUP for server in dns["nameserver"])
expected_dns_policies, expected_dns_providers = clash_dns_policies(clash["rules"])
assert dns["nameserver-policy"] == expected_dns_policies
assert list(dns["nameserver-policy"]) == list(expected_dns_policies)
assert clash["rule-providers"] == expected_dns_providers
stash_dns = stash["dns"]
assert stash_dns["follow-rule"] is True
assert stash_dns["nameserver-policy"]["geosite:cn"] == "https://223.5.5.5/dns-query"
assert all(server.startswith("https://") for key in ("default-nameserver", "proxy-server-nameserver", "nameserver", "fallback") for server in stash_dns[key])
assert clash["rules"][-1] == f"MATCH,{FINAL_GROUP}"
block_policy = "🛑 广告拦截"
app_policy = "🍃 应用净化"
assert any(rule.endswith(f",{block_policy}") for rule in clash["rules"])
assert clash["rules"].index("DOMAIN-SUFFIX,cn,DIRECT") > next(
    i for i, rule in enumerate(clash["rules"]) if rule.endswith(f",{block_policy}")
)
assert set(personal) == {"rules"}
assert isinstance(personal["rules"], list)
assert len(personal["rules"]) == len(set(personal["rules"]))
assert personal["rules"] == personal_routes + [with_policy(rule, "DIRECT") for rule in personal_rules]
for rule_set in (clash["rules"], stash["rules"]):
    for rule, _ in custom:
        if not rule.startswith("URL-REGEX,"):
            rendered = rule.replace(",Proxy", f",{PROXY_GROUP}")
            assert rule_set.index(f"DOMAIN-SUFFIX,a.youdao.com,{app_policy}") < rule_set.index(rendered) < rule_set.index("DOMAIN-SUFFIX,cn,DIRECT")
route = singbox["route"]
assert route["final"] == FINAL_GROUP
assert route["default_domain_resolver"]["server"] == "local"
dns_servers = {server["tag"]: server for server in singbox["dns"]["servers"]}
assert dns_servers["local"]["server"] == "223.5.5.5" and dns_servers["local"]["detour"] == "direct"
assert dns_servers["remote"]["server"] == "1.1.1.1" and dns_servers["remote"]["detour"] in group_names
assert dns_servers["remote-google"]["server"] == "8.8.8.8" and dns_servers["remote-google"]["detour"] in group_names
assert dns_servers["remote"]["detour"] == FINAL_GROUP
assert dns_servers["remote-google"]["detour"] == FINAL_GROUP
assert dns_servers[singbox["dns"]["rules"][1]["server"]]["detour"] == PROXY_GROUP
domain_fields = ("domain", "domain_suffix", "domain_keyword")
route_domain_projection = [
    (field, value, rule["outbound"])
    for rule in route["rules"] for field in domain_fields
    for value in rule.get(field, [])
]
dns_domain_projection = [
    (field, value, "block" if rule.get("action") == "reject"
     else dns_servers[rule["server"]]["detour"])
    for rule in singbox["dns"]["rules"][2:] for field in domain_fields
    for value in rule.get(field, [])
]
assert dns_domain_projection == route_domain_projection
flat_rules = []
for rule in route["rules"]:
    fields = [key for key in rule if key not in ("outbound", "action")]
    if len(fields) == 1 and isinstance(rule[fields[0]], list):
        for value in rule[fields[0]]:
            flat_rules.append({**rule, fields[0]: [value]})
    else:
        flat_rules.append(rule)
assert len(flat_rules) > 1000
assert len(route["rules"]) < len(flat_rules) / 2
assert {outbound["tag"] for outbound in singbox["outbounds"]} == set(group_names) | {"direct", "block"}
assert [outbound["tag"] for outbound in singbox["outbounds"][:len(DISPLAY_FIRST)]] == list(DISPLAY_FIRST)
singbox_outbounds = {outbound["tag"]: outbound for outbound in singbox["outbounds"]}
assert "direct" in singbox_outbounds[PROXY_GROUP]["outbounds"]
assert singbox_outbounds[PROXY_GROUP]["include"] == "~(?!)~u"
assert singbox_outbounds[auto_group]["type"] == "urltest"
for name, default in APP_DEFAULTS.items():
    outbound = singbox_outbounds[name]
    assert outbound["default"] == ("direct" if default == "DIRECT" else default)
    assert outbound["outbounds"][0] == outbound["default"]
    assert set(outbound["outbounds"]) == {PROXY_GROUP, *REGION_GROUPS, "direct"}
    assert "include" not in outbound
for name in REGION_GROUPS:
    outbound = singbox_outbounds[name]
    assert outbound["include"] == groups[name]["proxies"][1]
    assert outbound["fallback"] == "block"
for name in (*BLOCK_GROUPS, FINAL_GROUP):
    assert singbox_outbounds[name]["include"] == "~(?!)~u"
for rule, policy in custom:
    converted = singbox_rule(rule, policy)
    if converted is not None:
        assert converted in flat_rules
assert "[Proxy]" in surge and "[Rule]" in surge
assert surge.rstrip().endswith(f"FINAL,{FINAL_GROUP}")
assert "encrypted-dns-server = https://1.1.1.1/dns-query, https://8.8.8.8/dns-query" in surge
assert "encrypted-dns-follow-outbound-mode = true" in surge
assert "deepseek.com = server:https://223.5.5.5/dns-query" in surge
assert f"IP-CIDR,1.1.1.1/32,{AUTO_GROUP}" in surge
assert f"IP-CIDR,8.8.8.8/32,{AUTO_GROUP}" in surge
assert "IP-CIDR,223.5.5.5/32,DIRECT" in surge
surge_hosts = [line.split(" = ", 1) for line in surge.split("[Host]\n", 1)[1]
               .split("\n[Rule]", 1)[0].splitlines() if " = " in line]


def surge_dns_server(domain: str) -> str:
    for pattern, result in surge_hosts:
        if fnmatchcase(domain, pattern):
            return result
    return "default"


assert surge_dns_server("deepseek.com") == "server:https://223.5.5.5/dns-query"
assert surge_dns_server("alt1-mtalk.google.com") == "server:https://1.1.1.1/dns-query"
assert surge_dns_server("probe.alt1-mtalk.google.com") == "server:https://223.5.5.5/dns-query"
assert "[Proxy]" in surfboard and "[Rule]" in surfboard
assert surfboard.rstrip().endswith(f"FINAL,{FINAL_GROUP}")
assert "doh-server = https://223.5.5.5/dns-query" in surfboard
assert "dns-server =" not in surfboard
for content in (surge, surfboard):
    displayed = [line.split(" = ", 1)[0] for line in content.split("[Proxy Group]\n", 1)[1]
                 .split("\n[Host]", 1)[0].splitlines() if " = " in line]
    assert displayed[:len(DISPLAY_FIRST)] == list(DISPLAY_FIRST)
    assert displayed[-1] == FINAL_GROUP
    assert f"{PROXY_GROUP} = select, {auto_group}," in content
    assert f"{FINAL_GROUP} = select, {PROXY_GROUP}," in content
    assert f"{DIRECT_GROUP} =" not in content
    assert REMOVED_GROUP not in displayed
    for name, default in APP_DEFAULTS.items():
        line = next(line for line in content.splitlines() if line.startswith(name + " = "))
        members = line.split(" = select, ", 1)[1].split(", ")
        assert members[0] == default
        assert set(members) == {PROXY_GROUP, *REGION_GROUPS, "DIRECT", "$proxy_group"}
    for name in REGION_GROUPS:
        line = next(line for line in content.splitlines() if line.startswith(name + " = "))
        assert "include-all-proxies=true" in line and "policy-regex-filter=" in line
for content in (surge, surfboard, shadow):
    for rule, _ in custom:
        if content is surfboard and rule.startswith("URL-REGEX,"):
            continue
        rendered = rule.replace(",Proxy", ",PROXY" if content is shadow else f",{PROXY_GROUP}")
        reject = "REJECT" if content is shadow else app_policy
        assert content.index(f"DOMAIN-SUFFIX,a.youdao.com,{reject}") < content.index(rendered) < content.index("DOMAIN-SUFFIX,cn,DIRECT")
assert "[Rule]" in shadow and "[Host]" in shadow
assert "dns-server = https://1.1.1.1/dns-query#proxy, https://8.8.8.8/dns-query#proxy" in shadow
assert "direct-dns-server = https://223.5.5.5/dns-query" in shadow
assert "proxy-dns-server = https://223.5.5.5/dns-query" in shadow
assert "always-ip-address = true" in shadow
assert "dns-direct-fallback-proxy = false" in shadow
for content in (clash, clashmeta, stash, singbox, surge, surfboard):
    rendered = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    assert SOURCE_PROXY_GROUP not in rendered and SOURCE_AUTO_GROUP not in rendered
assert "RULE-SET,https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list,DIRECT" in shadow
assert shadow.index("FINAL,PROXY") < shadow.index("[Host]")

# DNS endpoints must be HTTPS with literal IP hosts; URL fragments select
# the outbound and must not be mistaken for part of the resolver address.
for content in (clash, clashmeta, stash, singbox, surge, surfboard, shadow):
    if isinstance(content, dict):
        config_dns = content["dns"]
        if "servers" in config_dns:
            for server in config_dns["servers"]:
                assert server["type"] == "https"
                ip_address(server["server"])
            continue
        endpoints = []
        for key in ("default-nameserver", "proxy-server-nameserver", "direct-nameserver", "nameserver", "fallback"):
            endpoints.extend(config_dns.get(key, []))
        for servers in config_dns.get("nameserver-policy", {}).values():
            endpoints.extend(servers if isinstance(servers, list) else [servers])
    else:
        endpoints = re.findall(r"https://[^\s,]+/dns-query", content)
    assert endpoints
    for endpoint in endpoints:
        parsed = urlsplit(endpoint)
        assert parsed.scheme == "https"
        ip_address(parsed.hostname)

print("Generated templates, ordered domain DNS policies, and IP DoH URLs validated")
