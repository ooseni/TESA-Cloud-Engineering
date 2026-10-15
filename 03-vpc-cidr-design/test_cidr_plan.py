"""Unit tests for cidr_plan.py. Run: python -m unittest discover -s 03-vpc-cidr-design -v"""
import ipaddress
import unittest

import cidr_plan as cp

net = ipaddress.ip_network


class Usable(unittest.TestCase):
    def test_aws_reserves_five_addresses_per_subnet(self):
        self.assertEqual(cp.usable(net("10.0.0.0/24")), 251)
        self.assertEqual(cp.usable(net("10.0.0.0/28")), 11)
        self.assertEqual(cp.usable(net("10.10.0.0/19")), 8_187)


class Split(unittest.TestCase):
    def test_six_subnets_round_up_to_eight_equal_slash_19s(self):
        blocks = cp.split(net("10.10.0.0/16"), 6)
        self.assertEqual(len(blocks), 8)
        self.assertTrue(all(b.prefixlen == 19 for b in blocks))
        self.assertEqual(str(blocks[0]), "10.10.0.0/19")
        self.assertEqual(str(blocks[-1]), "10.10.224.0/19")

    def test_a_split_below_slash_28_is_rejected(self):
        with self.assertRaises(ValueError):
            cp.split(net("10.0.0.0/24"), 32)   # would need /29


class Allocate(unittest.TestCase):
    REQUESTS = [(f"{tier} ({az})", prefix)
                for az in "abc" for tier, prefix in (("public", 24), ("app", 20), ("data", 22))]

    def test_every_subnet_is_inside_the_vpc_and_none_overlap(self):
        vpc = net("10.30.0.0/16")
        plan, free = cp.allocate(vpc, self.REQUESTS)
        self.assertEqual(len(plan), 9)
        nets = [s.network for s in plan]
        self.assertTrue(all(n.subnet_of(vpc) for n in nets))
        for i, a in enumerate(nets):
            for b in nets[i + 1:]:
                self.assertFalse(a.overlaps(b), f"{a} overlaps {b}")

    def test_allocated_plus_free_space_covers_the_vpc_exactly(self):
        vpc = net("10.30.0.0/16")
        plan, free = cp.allocate(vpc, self.REQUESTS)
        total = sum(s.network.num_addresses for s in plan) + sum(f.num_addresses for f in free)
        self.assertEqual(total, vpc.num_addresses)

    def test_largest_subnets_are_placed_first_and_aligned(self):
        plan, _ = cp.allocate(net("10.30.0.0/16"), self.REQUESTS)
        first = plan[0]
        self.assertEqual(first.network.prefixlen, 20)
        self.assertEqual(str(first.network), "10.30.0.0/20")

    def test_running_out_of_space_is_an_error(self):
        with self.assertRaises(ValueError):
            cp.allocate(net("10.0.0.0/24"), [("a", 25), ("b", 25), ("c", 25)])

    def test_subnets_outside_aws_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            cp.allocate(net("10.0.0.0/16"), [("tiny", 29)])
        with self.assertRaises(ValueError):
            cp.allocate(net("10.0.0.0/8"), [("vpc-too-big", 24)])


class Overlaps(unittest.TestCase):
    def test_a_vpc_that_overlaps_on_premises_is_reported(self):
        on_prem = [net("10.0.0.0/8"), net("192.168.0.0/16")]
        self.assertEqual(cp.overlaps(net("10.10.0.0/16"), on_prem), [net("10.0.0.0/8")])

    def test_a_clean_range_reports_nothing(self):
        self.assertEqual(cp.overlaps(net("172.31.0.0/16"), [net("10.0.0.0/8")]), [])


class Cli(unittest.TestCase):
    def test_plan_refuses_an_overlapping_vpc(self):
        code = cp.main(["plan", "10.10.0.0/16", "--azs", "a,b", "--tier", "app=20", "--avoid", "10.0.0.0/8"])
        self.assertEqual(code, 1)

    def test_bad_input_is_a_usage_error(self):
        self.assertEqual(cp.main(["split", "10.10.0.1/16", "--count", "4"]), 2)   # host bits set
        self.assertEqual(cp.main(["plan", "10.30.0.0/16", "--azs", "a", "--tier", "app"]), 2)


if __name__ == "__main__":
    unittest.main()
