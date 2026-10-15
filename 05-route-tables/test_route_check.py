"""Unit tests for route_check.py. Run: python -m unittest discover -s 05-route-tables -v

Each of the ten routing scenarios starts from the fixed bank VPC, breaks it the way the scenario
describes, and checks that the tool finds the fault and traces its effect."""
import contextlib
import copy
import io
import ipaddress
import json
import unittest
from pathlib import Path

import route_check as rc

HERE = Path(__file__).resolve().parent
FIXED = json.loads((HERE / "examples" / "bank-vpc.json").read_text(encoding="utf-8"))
AS_FOUND = json.loads((HERE / "examples" / "as-found.json").read_text(encoding="utf-8"))
ip = ipaddress.ip_address


def bank(change=None) -> rc.Vpc:
    """The fixed bank VPC, optionally broken by change(data)."""
    data = copy.deepcopy(FIXED)
    if change:
        change(data)
    return rc.Vpc(data)


def codes(vpc: rc.Vpc) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for f in vpc.audit():
        found.setdefault(f.code, set()).add(f.subject)
    return found


class AwsRules(unittest.TestCase):
    def test_every_route_table_gets_the_local_route(self):
        vpc = bank()
        for table in vpc.tables.values():
            self.assertIn(rc.Route(vpc.cidr, "local"), table.routes)

    def test_a_subnet_without_an_association_uses_the_main_route_table(self):
        vpc = bank(lambda d: d["route_tables"]["rt-data"]["subnets"].remove("data-b"))
        self.assertEqual(vpc.table_for("data-b").name, "rt-main")
        self.assertEqual(vpc.table_for("data-a").name, "rt-data")

    def test_longest_prefix_wins_and_a_broader_route_never_beats_local(self):
        table = rc.RouteTable("t", [rc.Route(ipaddress.ip_network("10.10.0.0/16"), "local"),
                                    rc.Route(ipaddress.ip_network("10.0.0.0/8"), "tgw"),
                                    rc.Route(ipaddress.ip_network("0.0.0.0/0"), "igw")])
        self.assertEqual(table.lookup(ip("10.10.30.10")).target, "local")
        self.assertEqual(table.lookup(ip("10.20.0.5")).target, "tgw")
        self.assertEqual(table.lookup(ip("8.8.8.8")).target, "igw")

    def test_a_subnet_can_only_have_one_route_table(self):
        with self.assertRaises(rc.ModelError):
            bank(lambda d: d["route_tables"]["rt-public"]["subnets"].append("data-a"))

    def test_a_route_more_specific_than_local_must_cover_a_whole_subnet(self):
        def half_subnet(d):
            d["gateways"]["fw"] = {"type": "appliance"}
            d["route_tables"]["rt-private-a"]["routes"]["10.10.30.0/25"] = "fw"
        with self.assertRaises(rc.ModelError):
            bank(half_subnet)

    def test_a_route_more_specific_than_local_cannot_point_at_an_internet_gateway(self):
        with self.assertRaises(rc.ModelError):
            bank(lambda d: d["route_tables"]["rt-private-a"]["routes"].update({"10.10.30.0/24": "igw"}))

    def test_the_vpc_range_can_only_be_the_local_route(self):
        with self.assertRaises(rc.ModelError):
            bank(lambda d: d["route_tables"]["rt-data"]["routes"].update({"10.10.0.0/16": "nat-a"}))

    def test_aws_reserved_addresses_are_refused(self):
        with self.assertRaises(rc.ModelError):
            bank(lambda d: d["resources"]["db-primary"].update(ip="10.10.30.1"))   # the VPC router


class FixedDesign(unittest.TestCase):
    def test_the_fixed_design_has_no_findings(self):
        self.assertEqual(bank().audit(), [])

    def test_the_full_trace_from_the_internet_to_the_database(self):
        vpc = bank()
        path = ["internet", "alb-node-a", "web-server-a", "app-server-a", "db-primary"]
        for src, dst in zip(path, path[1:]):
            self.assertEqual(vpc.trace(src, dst).outcome, "delivered", f"{src} -> {dst}")

    def test_each_hop_is_decided_by_the_route_table_of_the_subnet_it_leaves(self):
        hops = bank().trace("app-server-a", "db-primary").hops
        self.assertEqual((hops[0].at, hops[0].table), ("app-server-a", "rt-private-a"))
        self.assertEqual((hops[1].at, hops[1].table), ("db-primary", "rt-data"))   # the reply

    def test_outbound_goes_through_the_nat_gateway_in_the_same_zone(self):
        for az in "ab":
            hops = bank().trace(f"app-server-{az}", "internet").hops
            self.assertEqual(hops[0].route.target, f"nat-{az}")
            self.assertEqual(hops[1].route.target, "igw")

    def test_the_database_can_neither_reach_nor_be_reached_from_the_internet(self):
        vpc = bank()
        self.assertEqual(vpc.trace("internet", "db-primary").outcome, "dropped")
        self.assertEqual(vpc.trace("db-primary", "internet").outcome, "dropped")


class Scenarios(unittest.TestCase):
    def test_1_database_subnet_routes_to_the_internet_gateway(self):
        vpc = bank(lambda d: d["route_tables"]["rt-data"]["routes"].update({"0.0.0.0/0": "igw"}))
        self.assertEqual(codes(vpc)["isolated-subnet-routes-to-internet"], {"data-a", "data-b"})
        # the route alone does not expose it: without a public address the gateway cannot translate
        self.assertEqual(vpc.trace("internet", "db-primary").outcome, "dropped")
        self.assertEqual(vpc.trace("db-primary", "internet").outcome, "dropped")

    def test_2_internet_facing_subnet_has_no_route_to_the_internet_gateway(self):
        vpc = bank(lambda d: d["route_tables"]["rt-public"]["routes"].clear())
        found = codes(vpc)
        self.assertEqual(found["public-subnet-without-internet-route"], {"public-a", "public-b"})
        self.assertEqual(found["nat-gateway-without-internet-route"], {"nat-a", "nat-b"})
        trace = vpc.trace("internet", "alb-node-a")
        self.assertEqual(trace.outcome, "dropped")
        self.assertIn("no route back", trace.reason)    # the request arrives, the reply cannot leave

    def test_3_app_subnet_uses_the_public_route_table(self):
        def move(d):
            d["route_tables"]["rt-private-a"]["subnets"].remove("app-a")
            d["route_tables"]["rt-public"]["subnets"].append("app-a")
        vpc = bank(move)
        self.assertIn("app-a", codes(vpc)["private-subnet-routes-to-internet-gateway"])
        # app servers have no public address, so the symptom is broken payments, not exposure
        self.assertIn("no public IPv4", vpc.trace("app-server-a", "internet").reason)
        self.assertEqual(vpc.trace("internet", "app-server-a").outcome, "dropped")

    def test_4_all_tiers_share_one_route_table(self):
        vpc = rc.Vpc(AS_FOUND)
        found = codes(vpc)
        self.assertEqual(found["route-table-shared-across-tiers"], {"rt-main"})
        self.assertEqual(found["isolated-subnet-routes-to-internet"], {"data-a", "data-b"})

    def test_4_separate_route_tables_never_stop_traffic_between_tiers(self):
        # every route table has the local route, so tier-to-tier isolation is a job for
        # security groups and network ACLs, not route tables
        vpc = bank()
        self.assertEqual(vpc.trace("web-server-a", "db-primary").outcome, "delivered")

    def test_5_removing_every_default_route(self):
        def strip(d):
            for t in d["route_tables"].values():
                t["routes"].pop("0.0.0.0/0", None)
        vpc = bank(strip)
        found = codes(vpc)
        self.assertEqual(found["public-subnet-without-internet-route"], {"public-a", "public-b"})
        self.assertIn("app-a", found["no-outbound-route"])
        self.assertEqual(vpc.trace("app-server-a", "db-primary").outcome, "delivered")   # inside still works

    def test_5_a_vpc_with_no_internet_path_is_valid_when_nothing_needs_one(self):
        def offline(d):
            for t in d["route_tables"].values():
                t["routes"].pop("0.0.0.0/0", None)
            for s in d["subnets"].values():
                s["internet"] = "none"
            for r in d["resources"].values():
                r.pop("public_ip", None)
            d["gateways"] = {}
            d["flows"] = [f for f in d["flows"] if "internet" not in (f["from"], f["to"])]
        self.assertEqual(bank(offline).audit(), [])

    def test_6_internal_traffic_sent_to_an_appliance_one_way_only(self):
        def inspect(d):
            d["gateways"]["fw-a"] = {"type": "appliance"}
            d["route_tables"]["rt-private-a"]["routes"]["10.10.30.0/24"] = "fw-a"
        vpc = bank(inspect)
        self.assertEqual(vpc.trace("app-server-a", "db-primary").outcome, "handed-off")
        self.assertIn("rt-private-a", codes(vpc)["more-specific-than-local"])

    def test_6_internal_traffic_sent_to_a_deleted_appliance_is_a_blackhole(self):
        vpc = bank(lambda d: d["route_tables"]["rt-private-a"]["routes"].update({"10.10.30.0/24": "eni-gone"}))
        self.assertEqual(codes(vpc)["blackhole-route"], {"rt-private-a"})
        self.assertIn("app-server-a -> db-primary", codes(vpc)["flow-broken"])

    def test_6_replies_that_bypass_the_appliance_are_asymmetric(self):
        def one_way(d):
            d["gateways"]["fw-a"] = {"type": "appliance"}
            d["route_tables"]["rt-data"]["routes"]["10.10.20.0/24"] = "fw-a"
        trace = bank(one_way).trace("app-server-a", "db-primary")
        self.assertEqual(trace.outcome, "asymmetric")

    def test_7_web_cannot_reach_app(self):
        vpc = bank(lambda d: d["route_tables"]["rt-private-a"]["routes"].update({"10.10.20.0/24": "nat-gone"}))
        self.assertEqual(vpc.trace("web-server-a", "app-server-a").outcome, "dropped")
        self.assertIn("web-server-a -> app-server-a", codes(vpc)["flow-broken"])

    def test_8_database_reachable_from_the_internet(self):
        def expose(d):
            d["route_tables"]["rt-data"]["routes"]["0.0.0.0/0"] = "igw"
            d["resources"]["db-primary"]["public_ip"] = True    # RDS "Publicly accessible" = Yes
        vpc = bank(expose)
        self.assertEqual(vpc.trace("internet", "db-primary").outcome, "delivered")
        self.assertEqual(codes(vpc)["reachable-from-internet"], {"db-primary"})

    def test_8_a_public_address_alone_is_one_route_away_from_exposure(self):
        vpc = bank(lambda d: d["resources"]["db-primary"].update(public_ip=True))
        self.assertEqual(vpc.trace("internet", "db-primary").outcome, "dropped")
        self.assertEqual(codes(vpc)["public-ip-outside-public-tier"], {"db-primary"})

    def test_9_wrong_route_table_association(self):
        def swap(d):
            d["route_tables"]["rt-public"]["subnets"] = ["data-a", "data-b"]
            d["route_tables"]["rt-data"]["subnets"] = ["public-a", "public-b"]
        found = codes(bank(swap))
        self.assertEqual(found["isolated-subnet-routes-to-internet"], {"data-a", "data-b"})
        self.assertEqual(found["public-subnet-without-internet-route"], {"public-a", "public-b"})

    def test_9_a_main_route_table_with_an_internet_route_makes_new_subnets_public(self):
        vpc = bank(lambda d: d["route_tables"]["rt-main"]["routes"].update({"0.0.0.0/0": "igw"}))
        self.assertEqual(codes(vpc)["main-table-routes-to-internet"], {"rt-main"})

    def test_10_payment_calls_time_out_without_a_nat_route(self):
        vpc = bank(lambda d: d["route_tables"]["rt-private-a"]["routes"].clear())
        trace = vpc.trace("app-server-a", "internet")
        self.assertEqual(trace.outcome, "dropped")
        self.assertIn("no route to 203.0.113.10", trace.reason)
        self.assertIn("app-a", codes(vpc)["no-outbound-route"])

    def test_10_a_nat_gateway_in_a_private_subnet_cannot_reach_the_internet(self):
        vpc = bank(lambda d: d["gateways"]["nat-a"].update(subnet="app-a"))
        self.assertEqual(codes(vpc)["nat-gateway-without-internet-route"], {"nat-a"})
        self.assertEqual(vpc.trace("app-server-a", "internet").outcome, "dropped")

    def test_10_sharing_one_nat_gateway_across_zones_is_flagged(self):
        vpc = bank(lambda d: d["route_tables"]["rt-private-b"]["routes"].update({"0.0.0.0/0": "nat-a"}))
        self.assertEqual(codes(vpc)["nat-in-other-az"], {"web-b", "app-b"})


class AsFound(unittest.TestCase):
    def test_the_as_found_vpc_fails_the_audit(self):
        findings = rc.Vpc(AS_FOUND).audit()
        self.assertEqual(sum(f.severity == "critical" for f in findings), 6)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rc.main(["audit", str(HERE / "examples" / "as-found.json")]), 1)

    def test_the_fixed_vpc_passes_the_audit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rc.main(["audit", str(HERE / "examples" / "bank-vpc.json")]), 0)


if __name__ == "__main__":
    unittest.main()
