"""Regression checks for DNS routing priority and per-application bindings."""

import sys
import unittest
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
from build_rules import clash_dns_policies, singbox_dns_rules


def matches(rule: str, domain: str) -> bool:
    kind, value = rule.split(",", 1)
    return {
        "DOMAIN": domain == value,
        "DOMAIN-SUFFIX": domain == value or domain.endswith("." + value),
        "DOMAIN-KEYWORD": value in domain,
    }[kind]


class ClashDNSPolicies(unittest.TestCase):
    def resolve_policy(self, rules, domain):
        policies, providers = clash_dns_policies(rules)
        for key, servers in policies.items():
            provider = providers[key.removeprefix("rule-set:")]
            if any(matches(rule, domain) for rule in provider["payload"]):
                return {(urlsplit(server).hostname, urlsplit(server).fragment)
                        for server in servers}
        return None

    def test_applications_do_not_share_an_unrelated_dns_group(self):
        rules = ["DOMAIN-SUFFIX,ai.example,AI", "DOMAIN-SUFFIX,video.example,Video"]
        self.assertEqual(self.resolve_policy(rules, "api.ai.example"),
                         {("1.1.1.1", "AI"), ("8.8.8.8", "AI")})
        self.assertEqual(self.resolve_policy(rules, "www.video.example"),
                         {("1.1.1.1", "Video"), ("8.8.8.8", "Video")})

    def test_later_return_to_same_policy_does_not_move_a_rule_earlier(self):
        rules = ["DOMAIN,alpha.example,A", "DOMAIN-SUFFIX,example,B",
                 "DOMAIN,beta.example,A"]
        self.assertEqual({policy for _, policy in self.resolve_policy(rules, "beta.example")}, {"B"})

    def test_proxy_exception_precedes_broader_direct_suffix(self):
        rules = ["DOMAIN,alt1-mtalk.google.com,FCM", "DOMAIN-SUFFIX,google.com,DIRECT"]
        self.assertEqual({policy for _, policy in self.resolve_policy(rules, "alt1-mtalk.google.com")}, {"FCM"})
        self.assertEqual(self.resolve_policy(rules, "probe.alt1-mtalk.google.com"),
                         {("1.12.12.12", "DIRECT"), ("120.53.53.53", "DIRECT")})

    def test_keyword_priority_is_preserved(self):
        rules = ["DOMAIN-KEYWORD,video,Video", "DOMAIN-SUFFIX,example,DIRECT"]
        self.assertEqual({policy for _, policy in self.resolve_policy(rules, "video.example")}, {"Video"})


class SingBoxDNSPolicies(unittest.TestCase):
    def test_proxy_exception_is_not_lost_before_direct_rule(self):
        rules = [{"domain": ["proxy.example.cn"], "outbound": "AI"},
                 {"domain_suffix": ["cn"], "outbound": "direct"}]
        self.assertEqual(singbox_dns_rules(rules, {"AI": "ai-dns", "direct": "local"}),
                         [{"domain": ["proxy.example.cn"], "server": "ai-dns"},
                          {"domain_suffix": ["cn"], "server": "local"}])

    def test_literal_rejection_does_not_send_a_lookup(self):
        self.assertEqual(singbox_dns_rules([
            {"domain": ["blocked.example"], "outbound": "block"}], {}),
            [{"domain": ["blocked.example"], "action": "reject"}])


if __name__ == "__main__":
    unittest.main()
