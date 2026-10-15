"""Unit tests for filter_check.py. Run: python -m unittest discover -s 06-security-groups-nacls -v

Each of the ten scenarios starts from the fixed design, breaks it the way the scenario describes,
and checks both the finding and which layer stops the traffic."""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path

import filter_check as fc

HERE = Path(__file__).resolve().parent
FIXED = json.loads((HERE / "examples" / "bank-filters.json").read_text(encoding="utf-8"))
AS_FOUND = json.loads((HERE / "examples" / "as-found.json").read_text(encoding="utf-8"))


def bank(change=None) -> fc.Vpc:
    """The fixed design, optionally broken by change(data)."""
    data = copy.deepcopy(FIXED)
    if change:
        change(data)
    return fc.Vpc(data)


def codes(vpc: fc.Vpc) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for f in vpc.audit():
        found.setdefault(f.code, set()).add(f.subject)
    return found


def stopped_at(trace: fc.Trace) -> tuple[str, str, str]:
    bad = trace.first_failure
    return (bad.layer, bad.direction, bad.phase) if bad else ("", "", "")


def acl(*rows):
    return [{"rule": n, "protocol": p, "ports": ports, "cidr": cidr, "action": a} for n, p, ports, cidr, a in rows]


class AwsRules(unittest.TestCase):
    def test_the_first_matching_rule_wins(self):
        def deny_first(d):
            d["nacls"]["nacl-data"]["inbound"] = acl((90, "tcp", "5432", "10.40.20.0/23", "deny"),
                                                     (100, "tcp", "5432", "10.40.20.0/23", "allow"))
        self.assertEqual(stopped_at(bank(deny_first).trace("app-a", "db-a", 5432)),
                         ("nacl-data", "inbound", "request"))

    def test_a_later_deny_does_not_undo_an_earlier_allow(self):
        def allow_first(d):
            d["nacls"]["nacl-data"]["inbound"].append(
                {"rule": 200, "protocol": "tcp", "ports": "5432", "cidr": "10.40.20.0/23", "action": "deny"})
        self.assertTrue(bank(allow_first).trace("app-a", "db-a", 5432).allowed)

    def test_traffic_that_matches_no_rule_meets_the_star_rule(self):
        trace = bank().trace("internet", "db-a", 5432)
        self.assertIn("the * rule", trace.first_failure.detail)

    def test_the_default_network_acl_allows_everything_and_a_new_custom_one_nothing(self):
        default = fc.default_nacl()
        self.assertTrue(default.decide("inbound", "tcp", (22, 22), fc.INTERNET_IP)[0])
        empty = fc.Nacl("empty", [], [])
        self.assertFalse(empty.decide("inbound", "tcp", (443, 443), fc.INTERNET_IP)[0])

    def test_network_acls_do_not_see_traffic_within_a_subnet(self):
        def neighbour(d):
            d["resources"]["app-a2"] = {"subnet": "app-a", "ip": "10.40.20.11", "security_groups": ["sg-app"]}
            d["security_groups"]["sg-app"]["inbound"].append({"protocol": "tcp", "ports": "9000", "peer": "sg-app"})
            d["security_groups"]["sg-app"]["outbound"].append({"protocol": "tcp", "ports": "9000", "peer": "sg-app"})
        trace = bank(neighbour).trace("app-a", "app-a2", 9000)
        self.assertTrue(trace.allowed)
        self.assertEqual({c.kind for c in trace.checks}, {"sg"})

    def test_replies_need_the_whole_ephemeral_range(self):
        # AWS's example network ACL opens 32768-65535, but a load balancer uses 1024-65535
        def aws_example(d):
            d["nacls"]["nacl-web"]["outbound"][1]["ports"] = "32768-65535"
        trace = bank(aws_example).trace("alb-a", "web-a", 443)
        self.assertEqual(stopped_at(trace), ("nacl-web", "outbound", "reply"))
        self.assertIn("1024-32767", trace.first_failure.detail)

    def test_ephemeral_ranges_follow_the_client(self):
        vpc = bank()
        self.assertEqual(vpc.resources["alb-a"].client_ports, (1024, 65535))
        self.assertEqual(vpc.resources["nat-a"].client_ports, (1024, 65535))
        self.assertEqual(vpc.resources["app-a"].client_ports, (32768, 61000))

    def test_security_group_references_match_membership_not_addresses(self):
        rule = fc.SgRule("tcp", (5432, 5432), "sg-app")
        self.assertTrue(rule.matches("tcp", 5432, fc.INTERNET_IP, ("sg-app",)))
        self.assertFalse(rule.matches("tcp", 5432, fc.INTERNET_IP, ("sg-web",)))

    def test_a_nat_gateway_has_no_security_group_but_its_subnet_acl_applies_both_ways(self):
        trace = bank().trace("app-a", "internet", 443)
        layers = [(c.layer, c.direction, c.phase) for c in trace.checks]
        self.assertIn(("nacl-public", "inbound", "request"), layers)
        self.assertIn(("nacl-public", "outbound", "reply"), layers)
        with self.assertRaises(fc.ModelError):
            bank(lambda d: d["resources"]["nat-a"].update(security_groups=["sg-app"]))

    def test_invalid_rules_are_refused(self):
        with self.assertRaises(fc.ModelError):        # duplicate rule number in one direction
            bank(lambda d: d["nacls"]["nacl-app"]["inbound"].append(dict(d["nacls"]["nacl-app"]["inbound"][0])))
        with self.assertRaises(fc.ModelError):        # rule numbers run 1 to 32766
            bank(lambda d: d["nacls"]["nacl-app"]["inbound"][0].update(rule=40000))
        with self.assertRaises(fc.ModelError):        # a rule naming a security group that does not exist
            bank(lambda d: d["security_groups"]["sg-db"]["inbound"][0].update(peer="sg-missing"))


class FixedDesign(unittest.TestCase):
    def test_the_fixed_design_has_no_findings(self):
        self.assertEqual(bank().audit(), [])

    def test_security_groups_pass_replies_and_network_acls_need_rules_for_them(self):
        trace = bank().trace("app-a", "db-a", 5432)
        replies = [c for c in trace.checks if c.phase == "reply"]
        self.assertTrue(all("stateful" in c.detail for c in replies if c.kind == "sg"))
        self.assertTrue(all(c.detail.startswith("rule ") for c in replies if c.kind == "nacl"))
        self.assertEqual(len(trace.checks), 8)

    def test_four_independent_layers_stop_the_web_tier_reaching_the_database(self):
        trace = bank().trace("web-a", "db-a", 5432)
        self.assertEqual(sum(not c.allowed for c in trace.checks), 4)


class Scenarios(unittest.TestCase):
    def test_1_database_security_group_open_to_anywhere(self):
        vpc = bank(lambda d: d["security_groups"]["sg-db"]["inbound"][0].update(peer="0.0.0.0/0"))
        self.assertEqual(codes(vpc)["sg-inbound-from-anywhere"], {"sg-db"})
        # the data tier's network ACL still stops anything but the app subnets
        self.assertEqual(stopped_at(vpc.trace("internet", "db-a", 5432)), ("nacl-data", "inbound", "request"))

    def test_2_web_security_group_without_outbound_rules(self):
        vpc = bank(lambda d: d["security_groups"]["sg-web"].update(outbound=[]))
        self.assertEqual(stopped_at(vpc.trace("web-a", "app-a", 8080)), ("sg-web", "outbound", "request"))
        self.assertIn("web-a -> app-a tcp/8080", codes(vpc)["flow-blocked"])
        # replies to the load balancer still leave: a security group passes them without outbound rules
        self.assertTrue(vpc.trace("alb-a", "web-a", 443).allowed)

    def test_3_network_acl_denies_the_ephemeral_ports(self):
        vpc = bank(lambda d: d["nacls"]["nacl-app"]["inbound"].pop())
        self.assertEqual(stopped_at(vpc.trace("app-a", "db-a", 5432)), ("nacl-app", "inbound", "reply"))
        self.assertEqual(codes(vpc)["nacl-missing-return-ports"],
                         {"app-a -> db-a tcp/5432", "app-a -> internet tcp/443"})

    def test_4_app_security_group_allows_all_ports(self):
        def open_app(d):
            d["security_groups"]["sg-app"]["inbound"][0].update(protocol="all", ports="all")
            # usually with the web tier's default allow-all outbound rule left in place
            d["security_groups"]["sg-web"]["outbound"] = [{"protocol": "all", "ports": "all", "peer": "0.0.0.0/0"}]
        vpc = bank(open_app)
        self.assertEqual(codes(vpc)["sg-all-ports"], {"sg-app"})
        # port 22 now passes both security groups; only the network ACLs still stop it
        trace = vpc.trace("web-a", "app-a", 22)
        self.assertTrue(all(c.allowed for c in trace.checks if c.kind == "sg"))
        self.assertEqual(stopped_at(trace), ("nacl-web", "outbound", "request"))

    def test_5_a_database_with_no_outbound_rules_is_correct(self):
        vpc = bank()
        self.assertEqual(vpc.sgs["sg-db"].outbound, [])
        self.assertTrue(vpc.trace("app-a", "db-a", 5432).allowed)
        # the fix I first proposed, HTTPS out to anywhere, opens a path for stolen data
        opened = bank(lambda d: d["security_groups"]["sg-db"]["outbound"].append(
            {"protocol": "tcp", "ports": "443", "peer": "0.0.0.0/0"}))
        self.assertEqual(codes(opened)["data-tier-egress"], {"sg-db"})

    def test_6_web_tier_open_to_all_ports(self):
        vpc = bank(lambda d: d["security_groups"]["sg-web"]["inbound"][0].update(
            protocol="all", ports="all", peer="0.0.0.0/0"))
        found = codes(vpc)
        self.assertEqual(found["sg-all-ports"], {"sg-web"})
        self.assertEqual(found["sg-inbound-from-anywhere"], {"sg-web"})
        self.assertEqual(stopped_at(vpc.trace("internet", "web-a", 443)), ("nacl-web", "inbound", "request"))

    def test_7_network_acls_that_allow_everything(self):
        def defaults(d):
            for s in d["subnets"].values():
                if s["tier"] != "public":
                    s.pop("nacl")
        vpc = bank(defaults)
        self.assertEqual(codes(vpc)["nacl-allows-all"], {"default"})
        self.assertTrue(vpc.trace("app-a", "db-a", 5432).allowed)
        # with no guardrail, one wrong security group rule exposes the database
        both = bank(lambda d: (defaults(d), d["security_groups"]["sg-db"]["inbound"][0].update(peer="0.0.0.0/0")))
        self.assertIn("internet -> db-a tcp/5432", codes(both)["flow-not-blocked"])

    def test_8_the_bank_blocks_port_443(self):
        vpc = bank(lambda d: d["nacls"]["nacl-public"]["inbound"].insert(
            0, {"rule": 90, "protocol": "tcp", "ports": "443", "cidr": "0.0.0.0/0", "action": "deny"}))
        trace = vpc.trace("internet", "alb-a", 443)
        self.assertEqual(stopped_at(trace), ("nacl-public", "inbound", "request"))
        self.assertIn("rule 90", trace.first_failure.detail)
        self.assertIn("internet -> alb-a tcp/443", codes(vpc)["nacl-blocks-what-sg-allows"])
        # blocking 443 outbound from the app tier cuts off the payment provider instead
        egress = bank(lambda d: d["nacls"]["nacl-app"]["outbound"].insert(
            0, {"rule": 90, "protocol": "tcp", "ports": "443", "cidr": "0.0.0.0/0", "action": "deny"}))
        self.assertEqual(stopped_at(egress.trace("app-a", "internet", 443)), ("nacl-app", "outbound", "request"))

    def test_9_app_cannot_reach_the_database(self):
        vpc = bank(lambda d: d["security_groups"]["sg-db"]["inbound"][0].update(peer="sg-web"))
        self.assertEqual(stopped_at(vpc.trace("app-a", "db-a", 5432)), ("sg-db", "inbound", "request"))
        self.assertIn("app-a -> db-a tcp/5432", codes(vpc)["flow-blocked"])

    def test_10_security_groups_correct_but_a_network_acl_blocks(self):
        vpc = bank(lambda d: d["nacls"]["nacl-data"]["inbound"][0].update(ports="3306"))
        trace = vpc.trace("app-a", "db-a", 5432)
        self.assertEqual(stopped_at(trace), ("nacl-data", "inbound", "request"))
        self.assertTrue(all(c.allowed for c in trace.checks if c.kind == "sg"))
        self.assertEqual(codes(vpc)["nacl-blocks-what-sg-allows"], {"app-a -> db-a tcp/5432"})


class AsFound(unittest.TestCase):
    def test_the_as_found_design_fails_the_audit(self):
        findings = fc.Vpc(AS_FOUND).audit()
        self.assertEqual(sum(f.severity == "critical" for f in findings), 7)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fc.main(["audit", str(HERE / "examples" / "as-found.json")]), 1)

    def test_the_fixed_design_passes_the_audit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fc.main(["audit", str(HERE / "examples" / "bank-filters.json")]), 0)


if __name__ == "__main__":
    unittest.main()
