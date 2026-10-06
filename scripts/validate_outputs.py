#!/usr/bin/env python3
"""Check generated client files before publishing any XBoard template."""

import json
import sys
from pathlib import Path

import yaml
sys.dont_write_bytecode = True
from build_rules import (DIRECT_GROUP, FINAL_GROUP, PROXY_GROUP,
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
assert set(group_names) >= {PROXY_GROUP, FINAL_GROUP}
assert DIRECT_GROUP not in group_names and "🛑 全球拦截" not in group_names
groups = {group["name"]: group for group in clash["proxy-groups"]}
assert "DIRECT" in groups[PROXY_GROUP]["proxies"]
auto_group = groups[PROXY_GROUP]["proxies"][0]
assert groups[auto_group]["type"] == "url-test"
assert groups[auto_group]["filter"] == "(?:.*)"
assert set(group_names) >= {"💬 Ai平台", "🎥 奈飞视频", "🇭🇰 香港节点"}
assert "Hong Kong" in groups["🇭🇰 香港节点"]["filter"]
assert groups[auto_group]["interval"] > 0
assert groups[auto_group]["tolerance"] >= 0
assert isinstance(clash.get("rules"), list) and len(clash["rules"]) > 1000
assert stash == clash
assert {key: value for key, value in clashmeta.items() if key != "tun"} == clash
assert "enable" not in clashmeta["tun"]
assert clashmeta["tun"]["auto-route"] is True
assert clashmeta["tun"]["auto-detect-interface"] is True
assert set(clashmeta["tun"]["dns-hijack"]) == {"any:53", "tcp://any:53"}
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
singbox_outbounds = {outbound["tag"]: outbound for outbound in singbox["outbounds"]}
assert "direct" in singbox_outbounds[PROXY_GROUP]["outbounds"]
assert singbox_outbounds[auto_group]["type"] == "urltest"
for rule, policy in custom:
    converted = singbox_rule(rule, policy)
    if converted is not None:
        assert converted in flat_rules
assert "[Proxy]" in surge and "[Rule]" in surge
assert surge.rstrip().endswith(f"FINAL,{FINAL_GROUP}")
assert "[Proxy]" in surfboard and "[Rule]" in surfboard
assert surfboard.rstrip().endswith(f"FINAL,{FINAL_GROUP}")
for content in (surge, surfboard):
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
assert "RULE-SET,https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list,DIRECT" in shadow
assert shadow.index("FINAL,PROXY") < shadow.index("[Host]")

print("Generated six XBoard templates, Shadowrocket, and personal rules validated")
