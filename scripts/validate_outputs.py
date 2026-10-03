#!/usr/bin/env python3
"""Check generated client files before publishing any XBoard template."""

import json
import sys
from pathlib import Path

import yaml
sys.dont_write_bytecode = True
from build_rules import read_custom_rules, read_rules, singbox_rule


ROOT = Path(__file__).resolve().parents[1]
clash = yaml.safe_load((ROOT / "XBoard/clash.yaml").read_text(encoding="utf-8"))
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
assert "Proxy" in {group["name"] for group in clash["proxy-groups"]}
assert isinstance(clash.get("rules"), list) and len(clash["rules"]) > 1000
assert stash == clash
assert clash["rules"][-1] == "MATCH,Proxy"
assert any(rule.endswith(",REJECT") for rule in clash["rules"])
assert clash["rules"].index("DOMAIN-SUFFIX,cn,DIRECT") > next(
    i for i, rule in enumerate(clash["rules"]) if rule.endswith(",REJECT")
)
assert isinstance(personal.get("payload"), list)
assert len(personal["payload"]) == len(set(personal["payload"]))
assert personal["payload"] == personal_rules
for rule_set in (clash["rules"], stash["rules"]):
    for rule, _ in custom:
        if not rule.startswith("URL-REGEX,"):
            assert rule_set.index("DOMAIN-SUFFIX,a.youdao.com,REJECT") < rule_set.index(rule) < rule_set.index("DOMAIN-SUFFIX,cn,DIRECT")
route = singbox["route"]
assert route["final"] == "节点选择"
assert len(route["rules"]) > 1000
assert {outbound["tag"] for outbound in singbox["outbounds"]} >= {"节点选择", "自动选择", "direct", "block"}
for rule, policy in custom:
    converted = singbox_rule(rule, policy)
    if converted is not None:
        assert converted in route["rules"]
assert "[Proxy]" in surge and "[Rule]" in surge
assert surge.rstrip().endswith("FINAL,Proxy")
assert "[Proxy]" in surfboard and "[Rule]" in surfboard
assert surfboard.rstrip().endswith("FINAL,Proxy")
for content in (surge, surfboard, shadow):
    for rule, _ in custom:
        if content is surfboard and rule.startswith("URL-REGEX,"):
            continue
        rendered = rule.replace(",Proxy", ",PROXY") if content is shadow else rule
        assert content.index("DOMAIN-SUFFIX,a.youdao.com,REJECT") < content.index(rendered) < content.index("DOMAIN-SUFFIX,cn,DIRECT")
assert "[Rule]" in shadow and "[Host]" in shadow
assert "RULE-SET,https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list,DIRECT" in shadow
assert shadow.index("FINAL,PROXY") < shadow.index("[Host]")

print("Generated six XBoard templates, Shadowrocket, and personal rules validated")
