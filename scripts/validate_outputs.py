#!/usr/bin/env python3
"""Check generated client files before publishing any XBoard template."""

import json
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

import yaml
sys.dont_write_bytecode = True
from build_rules import (AUTO_GROUP, DIRECT_GROUP, DISPLAY_FIRST, FINAL_GROUP,
                         PROXY_GROUP, SOURCE_AUTO_GROUP, SOURCE_PROXY_GROUP,
                         read_custom_rules, read_rules, singbox_rule)


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
personal_rules = read_rules(personal_list, "Rules/Personal.list")

assert isinstance(clash.get("proxy-groups"), list)
group_names = [group["name"] for group in clash["proxy-groups"]]
assert group_names[:len(DISPLAY_FIRST)] == list(DISPLAY_FIRST)
assert group_names[-1] == FINAL_GROUP
assert set(group_names) >= {PROXY_GROUP, FINAL_GROUP}
assert DIRECT_GROUP not in group_names and "🛑 全球拦截" not in group_names
groups = {group["name"]: group for group in clash["proxy-groups"]}
assert "DIRECT" in groups[PROXY_GROUP]["proxies"]
auto_group = groups[PROXY_GROUP]["proxies"][0]
assert auto_group == AUTO_GROUP
assert groups[auto_group]["type"] == "url-test"
assert groups[auto_group]["proxies"] == []
assert groups["🚀 手动切换"]["proxies"] == []
assert set(group_names) >= {"💬 Ai平台", "🎥 奈飞视频", "🇭🇰 香港节点"}
hong_kong = groups["🇭🇰 香港节点"]["proxies"]
assert hong_kong[0] == "🚀 手动切换"
assert len(hong_kong) == 2 and hong_kong[1].startswith("~") and hong_kong[1].endswith("~u")
assert re.search(hong_kong[1][1:-2], "Hong Kong 01")
assert re.search(hong_kong[1][1:-2], "🇭🇰 01")
assert not re.search(hong_kong[1][1:-2], "Japan 01")
assert groups["🎥 奈飞节点"]["proxies"][0] == "🚀 手动切换"
assert all("include-all" not in group and "filter" not in group for group in groups.values())
assert groups[auto_group]["interval"] > 0
assert groups[auto_group]["tolerance"] >= 0
assert isinstance(clash.get("rules"), list) and len(clash["rules"]) > 1000
assert {key: value for key, value in stash.items() if key not in ("dns", "rules")} == {key: value for key, value in clash.items() if key not in ("dns", "rules")}
assert stash["rules"][3:] == clash["rules"]
assert stash["rules"][:3] == [
    f"DOMAIN,dns.cloudflare.com,{AUTO_GROUP}",
    f"DOMAIN,dns.google,{AUTO_GROUP}",
    "DOMAIN,dns.alidns.com,DIRECT",
]
assert {key: value for key, value in clashmeta.items() if key != "tun"} == clash
assert "enable" not in clashmeta["tun"]
assert clashmeta["tun"]["auto-route"] is True
assert clashmeta["tun"]["auto-detect-interface"] is True
assert set(clashmeta["tun"]["dns-hijack"]) == {"any:53", "tcp://any:53"}
dns = clash["dns"]
assert dns == clashmeta["dns"]
assert all(server.startswith("https://") for key in ("default-nameserver", "proxy-server-nameserver", "direct-nameserver", "nameserver", "fallback") for server in dns[key])
assert all("dns.alidns.com" in server or "223.5.5.5" in server for server in dns["direct-nameserver"] + dns["proxy-server-nameserver"])
assert all(server.endswith("#DIRECT") for server in dns["direct-nameserver"])
assert all(("dns.cloudflare.com" in server or "dns.google" in server) and server.endswith("#" + AUTO_GROUP) for server in dns["nameserver"] + dns["fallback"])
stash_dns = stash["dns"]
assert stash_dns["follow-rule"] is True
assert stash_dns["nameserver-policy"]["geosite:cn"] == "https://dns.alidns.com/dns-query"
assert all(server.startswith("https://") for key in ("default-nameserver", "proxy-server-nameserver", "nameserver", "fallback") for server in stash_dns[key])
assert clash["rules"][-1] == f"MATCH,{FINAL_GROUP}"
block_policy = "🛑 广告拦截"
app_policy = "🍃 应用净化"
assert any(rule.endswith(f",{block_policy}") for rule in clash["rules"])
assert clash["rules"].index("DOMAIN-SUFFIX,cn,DIRECT") > next(
    i for i, rule in enumerate(clash["rules"]) if rule.endswith(f",{block_policy}")
)
assert isinstance(personal.get("payload"), list)
assert len(personal["payload"]) == len(set(personal["payload"]))
assert personal["payload"] == personal_rules
for rule_set in (clash["rules"], stash["rules"]):
    for rule, _ in custom:
        if not rule.startswith("URL-REGEX,"):
            rendered = rule.replace(",Proxy", f",{PROXY_GROUP}")
            assert rule_set.index(f"DOMAIN-SUFFIX,a.youdao.com,{app_policy}") < rule_set.index(rendered) < rule_set.index("DOMAIN-SUFFIX,cn,DIRECT")
route = singbox["route"]
assert route["final"] == FINAL_GROUP
assert route["default_domain_resolver"]["server"] == "local"
dns_servers = {server["tag"]: server for server in singbox["dns"]["servers"]}
assert dns_servers["local"]["server"] == "dns.alidns.com" and dns_servers["local"]["detour"] == "direct"
assert dns_servers["remote"]["server"] == "dns.cloudflare.com" and dns_servers["remote"]["detour"] == AUTO_GROUP
assert dns_servers["remote-google"]["server"] == "dns.google" and dns_servers["remote-google"]["detour"] == AUTO_GROUP
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
assert singbox_outbounds[auto_group]["type"] == "urltest"
for rule, policy in custom:
    converted = singbox_rule(rule, policy)
    if converted is not None:
        assert converted in flat_rules
assert "[Proxy]" in surge and "[Rule]" in surge
assert surge.rstrip().endswith(f"FINAL,{FINAL_GROUP}")
assert "encrypted-dns-server = https://dns.cloudflare.com/dns-query, https://dns.google/dns-query" in surge
assert "encrypted-dns-follow-outbound-mode = true" in surge
assert "deepseek.com = server:https://dns.alidns.com/dns-query" in surge
assert f"DOMAIN,dns.cloudflare.com,{AUTO_GROUP}" in surge
assert f"DOMAIN,dns.google,{AUTO_GROUP}" in surge
assert "DOMAIN,dns.alidns.com,DIRECT" in surge
surge_hosts = [line.split(" = ", 1) for line in surge.split("[Host]\n", 1)[1]
               .split("\n[Rule]", 1)[0].splitlines() if " = " in line]


def surge_dns_server(domain: str) -> str:
    for pattern, result in surge_hosts:
        if fnmatchcase(domain, pattern):
            return result
    return "default"


assert surge_dns_server("deepseek.com") == "server:https://dns.alidns.com/dns-query"
assert surge_dns_server("alt1-mtalk.google.com") == "server:https://dns.cloudflare.com/dns-query"
assert surge_dns_server("probe.alt1-mtalk.google.com") == "server:https://dns.alidns.com/dns-query"
assert "[Proxy]" in surfboard and "[Rule]" in surfboard
assert surfboard.rstrip().endswith(f"FINAL,{FINAL_GROUP}")
assert "doh-server = https://dns.alidns.com/dns-query" in surfboard
assert "dns-server =" not in surfboard
for content in (surge, surfboard):
    displayed = [line.split(" = ", 1)[0] for line in content.split("[Proxy Group]\n", 1)[1]
                 .split("\n[Host]", 1)[0].splitlines() if " = " in line]
    assert displayed[:len(DISPLAY_FIRST)] == list(DISPLAY_FIRST)
    assert displayed[-1] == FINAL_GROUP
    assert f"{PROXY_GROUP} = select, {auto_group}," in content
    assert f"{FINAL_GROUP} = select, {PROXY_GROUP}," in content
    assert f"{DIRECT_GROUP} =" not in content
for content in (surge, surfboard, shadow):
    for rule, _ in custom:
        if content is surfboard and rule.startswith("URL-REGEX,"):
            continue
        rendered = rule.replace(",Proxy", ",PROXY" if content is shadow else f",{PROXY_GROUP}")
        reject = "REJECT" if content is shadow else app_policy
        assert content.index(f"DOMAIN-SUFFIX,a.youdao.com,{reject}") < content.index(rendered) < content.index("DOMAIN-SUFFIX,cn,DIRECT")
assert "[Rule]" in shadow and "[Host]" in shadow
for content in (clash, clashmeta, stash, singbox, surge, surfboard):
    rendered = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    assert SOURCE_PROXY_GROUP not in rendered and SOURCE_AUTO_GROUP not in rendered
assert "RULE-SET,https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list,DIRECT" in shadow
assert shadow.index("FINAL,PROXY") < shadow.index("[Host]")

print("Generated six XBoard templates, Shadowrocket, and personal rules validated")
