#!/usr/bin/env python3
"""Plan VPC subnets: split a CIDR block, or allocate right-sized subnets per tier and Availability Zone.

Every subnet is checked against AWS's limits (/16 to /28) and reports its usable addresses, which is
the block size minus the 5 addresses AWS reserves in every subnet: the network address, the VPC
router, the DNS server, one held for future use, and the broadcast address.

Examples:
    python cidr_plan.py split 10.10.0.0/16 --count 6
    python cidr_plan.py plan 10.30.0.0/16 --azs a,b,c --tier public=24 --tier app=20 --tier data=22 \\
        --avoid 10.0.0.0/16 --avoid 172.16.0.0/12
"""
from __future__ import annotations

import argparse
import ipaddress
import sys
from dataclasses import dataclass

AWS_RESERVED = 5
MIN_PREFIX, MAX_PREFIX = 16, 28

Network = ipaddress.IPv4Network


@dataclass(frozen=True)
class Subnet:
    name: str
    network: Network

    @property
    def usable(self) -> int:
        return usable(self.network)


def usable(net: Network) -> int:
    """Addresses an EC2 instance or ENI can actually use in this subnet."""
    return net.num_addresses - AWS_RESERVED


def parse_network(text: str) -> Network:
    try:
        net = ipaddress.ip_network(text, strict=True)
    except ValueError as exc:
        raise ValueError(f"'{text}' is not a valid network address: {exc}") from None
    if net.version != 4:
        raise ValueError(f"'{text}' is IPv6; this tool plans IPv4 VPC ranges")
    return net


def check_prefix(prefix: int, what: str) -> None:
    if not MIN_PREFIX <= prefix <= MAX_PREFIX:
        raise ValueError(f"{what} must be between /{MIN_PREFIX} and /{MAX_PREFIX} on AWS, got /{prefix}")


def split(vpc: Network, count: int) -> list[Network]:
    """Split vpc into equal blocks, rounding count up to the next power of two."""
    if count < 1:
        raise ValueError("count must be at least 1")
    bits = (count - 1).bit_length()
    check_prefix(vpc.prefixlen + bits, "the resulting subnet size")
    return list(vpc.subnets(prefixlen_diff=bits))


def allocate(vpc: Network, requests: list[tuple[str, int]]) -> tuple[list[Subnet], list[Network]]:
    """Allocate one subnet per (name, prefix) request inside vpc, with no overlaps.

    Requests are placed largest first, each into the smallest free block that can hold it, so blocks
    stay aligned and free space stays in as few pieces as possible. Returns the subnets in address
    order and the free blocks left over.
    """
    check_prefix(vpc.prefixlen, "the VPC CIDR")
    free: list[Network] = [vpc]
    plan: list[Subnet] = []
    for name, prefix in sorted(requests, key=lambda r: r[1]):
        check_prefix(prefix, f"subnet '{name}'")
        if prefix < vpc.prefixlen:
            raise ValueError(f"subnet '{name}' (/{prefix}) is larger than the VPC {vpc}")
        fits = [b for b in free if b.prefixlen <= prefix]
        if not fits:
            raise ValueError(f"no room left in {vpc} for subnet '{name}' (/{prefix})")
        block = min(fits, key=lambda b: (-b.prefixlen, int(b.network_address)))
        free.remove(block)
        subnet = next(block.subnets(new_prefix=prefix))
        free.extend(block.address_exclude(subnet))
        plan.append(Subnet(name, subnet))
    plan.sort(key=lambda s: int(s.network.network_address))
    return plan, sorted(free, key=lambda b: int(b.network_address))


def overlaps(vpc: Network, others: list[Network]) -> list[Network]:
    """The ranges in others that overlap vpc (for example on-premises networks or other VPCs)."""
    return [o for o in others if vpc.overlaps(o)]


def table(rows: list[tuple[str, Network]]) -> str:
    lines = ["| Subnet | CIDR | Range | Usable addresses |", "|---|---|---|---:|"]
    for name, net in rows:
        lines.append(f"| {name} | `{net}` | {net.network_address} to {net.broadcast_address} | {usable(net):,} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("split", help="split a CIDR into equal blocks")
    sp.add_argument("cidr")
    sp.add_argument("--count", type=int, required=True, help="blocks needed (rounded up to a power of two)")

    pp = sub.add_parser("plan", help="allocate one subnet per tier per Availability Zone")
    pp.add_argument("cidr")
    pp.add_argument("--azs", required=True, help="comma-separated AZ suffixes, e.g. a,b,c")
    pp.add_argument("--tier", action="append", required=True, metavar="NAME=PREFIX",
                    help="a tier and its subnet prefix length, e.g. app=20 (repeatable)")
    pp.add_argument("--avoid", action="append", default=[], metavar="CIDR",
                    help="a range the VPC must not overlap, e.g. on premises (repeatable)")

    args = ap.parse_args(argv)
    try:
        vpc = parse_network(args.cidr)
        if args.command == "split":
            blocks = split(vpc, args.count)
            print(f"{vpc} split into {len(blocks)} blocks of /{blocks[0].prefixlen} "
                  f"({args.count} needed, {len(blocks) - args.count} spare):\n")
            print(table([(f"Block {i}", b) for i, b in enumerate(blocks, 1)]))
            return 0

        clashes = overlaps(vpc, [parse_network(a) for a in args.avoid])
        if clashes:
            print(f"error: {vpc} overlaps {', '.join(map(str, clashes))}; choose another VPC range",
                  file=sys.stderr)
            return 1
        tiers = []
        for spec in args.tier:
            name, _, prefix = spec.partition("=")
            if not name or not prefix.isdigit():
                raise ValueError(f"--tier expects NAME=PREFIX, got '{spec}'")
            tiers.append((name, int(prefix)))
        azs = [a.strip() for a in args.azs.split(",") if a.strip()]
        requests = [(f"{name} ({az})", prefix) for az in azs for name, prefix in tiers]
        plan, free = allocate(vpc, requests)
        print(table([(s.name, s.network) for s in plan]))
        used = sum(s.network.num_addresses for s in plan)
        print(f"\nAllocated {used:,} of {vpc.num_addresses:,} addresses "
              f"({used / vpc.num_addresses:.0%}); free blocks: {', '.join(map(str, free)) or 'none'}")
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
