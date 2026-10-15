#!/usr/bin/env python3
"""Check a VPC's routing the way the VPC router does, before anything is built.

The VPC is described in a JSON file: subnets, route tables, gateways and the resources in them.
The tool follows AWS's routing rules:
- each subnet uses its explicitly associated route table, or else the main route table;
- every route table has a local route for the VPC's CIDR block;
- the most specific matching route wins (longest prefix match);
- a route more specific than the local route must cover a whole subnet and point at a NAT gateway,
  a network interface or a Gateway Load Balancer endpoint;
- an internet gateway only carries IPv4 traffic for resources with a public IPv4 address.

It traces a connection hop by hop (which route table decides, which route matches, where the packet
goes) and audits the design for the routing mistakes that expose a bank's data or break its payments.
It checks routing only: security groups and network ACLs are module 06.

Examples:
    python route_check.py tables examples/bank-vpc.json
    python route_check.py trace examples/bank-vpc.json internet alb-node-a web-server-a app-server-a db-primary
    python route_check.py trace examples/bank-vpc.json app-server-a internet
    python route_check.py audit examples/as-found.json
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

INTERNET = "internet"
INTERNET_IP = ipaddress.ip_address("203.0.113.10")   # documentation range (RFC 5737)
INTENTS = ("public", "outbound", "none")              # what a subnet should be able to do on the internet
GATEWAY_TYPES = ("internet", "nat", "appliance", "transit", "peering", "vpn")
MORE_SPECIFIC_TARGETS = ("nat", "appliance")          # NAT gateway, network interface, GWLB endpoint
SEVERITIES = ("critical", "high", "medium", "low", "info")

Network = ipaddress.IPv4Network
Address = ipaddress.IPv4Address


class ModelError(ValueError):
    """The JSON describes something AWS would refuse to create."""


@dataclass(frozen=True)
class Route:
    destination: Network
    target: str

    def __str__(self) -> str:
        return f"{self.destination} -> {self.target}"


@dataclass
class RouteTable:
    name: str
    routes: list[Route]
    subnets: list[str] = field(default_factory=list)
    main: bool = False

    def lookup(self, address: Address) -> Route | None:
        """The most specific route that matches the address, as the VPC router picks it."""
        matches = [r for r in self.routes if address in r.destination]
        return max(matches, key=lambda r: r.destination.prefixlen, default=None)


@dataclass(frozen=True)
class Subnet:
    name: str
    network: Network
    az: str
    internet: str


@dataclass(frozen=True)
class Gateway:
    name: str
    type: str
    subnet: str | None = None


@dataclass(frozen=True)
class Resource:
    name: str
    subnet: str
    ip: Address
    public_ip: bool = False


@dataclass(frozen=True)
class Hop:
    at: str
    table: str | None
    route: Route | None
    note: str

    def __str__(self) -> str:
        where = f"{self.at:<13}"
        if self.table:
            matched = str(self.route) if self.route else "no matching route"
            where += f" {self.table:<13} {matched:<26}"
        return f"{where} {self.note}".rstrip()


@dataclass
class Trace:
    source: str
    destination: str
    hops: list[Hop]
    outcome: str        # delivered | dropped | handed-off | left-vpc | asymmetric
    reason: str

    @property
    def reachable(self) -> bool:
        return self.outcome in ("delivered", "asymmetric", "handed-off", "left-vpc")


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    subject: str
    message: str


def _network(text: str, what: str) -> Network:
    try:
        net = ipaddress.ip_network(text, strict=True)
    except ValueError as exc:
        raise ModelError(f"{what}: '{text}' is not a valid IPv4 network ({exc})") from None
    if net.version != 4:
        raise ModelError(f"{what}: '{text}' is IPv6; this tool checks IPv4 routing")
    return net


class Vpc:
    def __init__(self, data: dict):
        vpc = data.get("vpc", {})
        self.name = vpc.get("name", "vpc")
        self.cidr = _network(vpc.get("cidr", ""), "VPC CIDR")
        if not 16 <= self.cidr.prefixlen <= 28:
            raise ModelError(f"VPC CIDR {self.cidr} must be between /16 and /28")

        self.subnets: dict[str, Subnet] = {}
        for name, s in data.get("subnets", {}).items():
            net = _network(s.get("cidr", ""), f"subnet {name}")
            if not net.subnet_of(self.cidr):
                raise ModelError(f"subnet {name} ({net}) is outside the VPC ({self.cidr})")
            clash = next((o for o in self.subnets.values() if o.network.overlaps(net)), None)
            if clash:
                raise ModelError(f"subnet {name} ({net}) overlaps {clash.name} ({clash.network})")
            intent = s.get("internet", "none")
            if intent not in INTENTS:
                raise ModelError(f"subnet {name}: internet must be one of {', '.join(INTENTS)}")
            self.subnets[name] = Subnet(name, net, s.get("az", ""), intent)

        self.gateways: dict[str, Gateway] = {}
        for name, g in data.get("gateways", {}).items():
            if g.get("type") not in GATEWAY_TYPES:
                raise ModelError(f"gateway {name}: type must be one of {', '.join(GATEWAY_TYPES)}")
            if g["type"] == "nat" and g.get("subnet") not in self.subnets:
                raise ModelError(f"NAT gateway {name} must name the subnet it lives in")
            self.gateways[name] = Gateway(name, g["type"], g.get("subnet"))

        self.tables: dict[str, RouteTable] = {}
        owner: dict[str, str] = {}
        for name, t in data.get("route_tables", {}).items():
            routes = [self._route(name, dest, target) for dest, target in t.get("routes", {}).items()]
            if not any(r.destination == self.cidr for r in routes):
                routes.insert(0, Route(self.cidr, "local"))     # every route table has the local route
            for s in t.get("subnets", []):
                if s not in self.subnets:
                    raise ModelError(f"route table {name} is associated with unknown subnet {s}")
                if s in owner:
                    raise ModelError(f"subnet {s} is associated with both {owner[s]} and {name}; "
                                     "a subnet uses one route table at a time")
                owner[s] = name
            self.tables[name] = RouteTable(name, routes, list(t.get("subnets", [])), bool(t.get("main")))
        mains = [t for t in self.tables.values() if t.main]
        if len(mains) != 1:
            raise ModelError(f"a VPC has exactly one main route table; found {len(mains)}")
        self.main_table = mains[0]
        self._explicit = owner

        self.resources: dict[str, Resource] = {}
        for name, r in data.get("resources", {}).items():
            if r.get("subnet") not in self.subnets:
                raise ModelError(f"resource {name} is in unknown subnet {r.get('subnet')}")
            ip = ipaddress.ip_address(r.get("ip", ""))
            net = self.subnets[r["subnet"]].network
            if ip not in net or ip in (net[0], net[1], net[2], net[3], net[-1]):
                raise ModelError(f"resource {name}: {ip} is not a usable address in {net} "
                                 "(AWS reserves the first four and the last)")
            self.resources[name] = Resource(name, r["subnet"], ip, bool(r.get("public_ip")))

        self.flows = list(data.get("flows", []))

    def _route(self, table: str, dest: str, target: str) -> Route:
        net = _network(dest, f"route table {table}")
        gateway = self.gateways.get(target)
        if net == self.cidr and target != "local":
            raise ModelError(f"route table {table}: {net} is the VPC's own range; it can only be the local route")
        if net != self.cidr and net.subnet_of(self.cidr):
            # AWS accepts a route more specific than the local route only for a whole subnet,
            # pointing at a NAT gateway, a network interface or a Gateway Load Balancer endpoint
            if not any(s.network == net for s in self.subnets.values()):
                raise ModelError(f"route table {table}: {net} is inside the VPC but is not a subnet's "
                                 "whole CIDR block, which AWS requires of a route more specific than local")
            if gateway is not None and gateway.type not in MORE_SPECIFIC_TARGETS:
                raise ModelError(f"route table {table}: a route for subnet {net} must point at a NAT gateway, "
                                 f"network interface or Gateway Load Balancer endpoint, not {target}")
        return Route(net, target)

    # ------------------------------------------------------------ lookups
    def table_for(self, subnet: str) -> RouteTable:
        """The subnet's route table: its explicit association, or else the main route table."""
        name = self._explicit.get(subnet)
        return self.tables[name] if name else self.main_table

    def is_implicit(self, subnet: str) -> bool:
        return subnet not in self._explicit

    def address(self, name: str) -> Address:
        if name == INTERNET:
            return INTERNET_IP
        if name in self.resources:
            return self.resources[name].ip
        try:
            return ipaddress.ip_address(name)
        except ValueError:
            raise ModelError(f"'{name}' is not a resource, an IP address or 'internet'") from None

    def resource_at(self, ip: Address) -> Resource | None:
        return next((r for r in self.resources.values() if r.ip == ip), None)

    def gateway_type(self, target: str) -> str | None:
        if target == "local":
            return "local"
        gw = self.gateways.get(target)
        return gw.type if gw else None

    def reaches_internet_gateway(self, subnet: str) -> bool:
        route = self.table_for(subnet).lookup(INTERNET_IP)
        return route is not None and self.gateway_type(route.target) == "internet"

    # ------------------------------------------------------------ tracing
    def trace(self, source: str, destination: str) -> Trace:
        if source == INTERNET:
            return self._trace_inbound(destination)
        if source not in self.resources:
            raise ModelError(f"unknown source '{source}'")
        res = self.resources[source]
        dst = self.address(destination)
        table = self.table_for(res.subnet)
        route = table.lookup(dst)
        hops: list[Hop] = []

        def done(outcome, reason):
            return Trace(source, destination, hops, outcome, reason)

        if route is None:
            hops.append(Hop(source, table.name, None, "dropped"))
            return done("dropped", f"{table.name} has no route to {dst}")
        kind = self.gateway_type(route.target)
        if kind is None:
            hops.append(Hop(source, table.name, route, "blackhole"))
            return done("dropped", f"{route.target} does not exist, so the route is a blackhole")

        if kind == "local":
            hops.append(Hop(source, table.name, route, "local delivery inside the VPC"))
            peer = self.resource_at(dst)
            if peer is None:
                return done("dropped", f"nothing in the VPC holds {dst}")
            back_table = self.table_for(peer.subnet)
            back = back_table.lookup(res.ip)
            hops.append(Hop(peer.name, back_table.name, back, "reply"))
            if back is None or back.target != "local":
                return done("asymmetric", f"the reply from {peer.name} leaves by {back.target if back else 'no route'}, "
                                          "not the way the request came")
            return done("delivered", f"{source} reaches {peer.name} over the local route")

        if kind == "internet":
            if not res.public_ip:
                hops.append(Hop(source, table.name, route, "dropped at the internet gateway"))
                return done("dropped", f"{source} has no public IPv4 address, so the internet gateway "
                                       "cannot translate its traffic")
            hops.append(Hop(source, table.name, route, "translated to its public IPv4 address"))
            return done("delivered", f"{source} reaches {destination} through {route.target}")

        if kind == "nat":
            hops.append(Hop(source, table.name, route, "to the NAT gateway"))
            gw = self.gateways[route.target]
            nat_table = self.table_for(gw.subnet)
            onward = nat_table.lookup(dst)
            if onward is None or self.gateway_type(onward.target) != "internet":
                hops.append(Hop(gw.name, nat_table.name, onward, "dropped"))
                return done("dropped", f"{gw.name}'s subnet {gw.subnet} has no route to an internet gateway")
            hops.append(Hop(gw.name, nat_table.name, onward, "translated to the NAT gateway's Elastic IP"))
            return done("delivered", f"{source} reaches {destination} through {gw.name} and {onward.target}")

        hops.append(Hop(source, table.name, route, f"to {route.target}"))
        if kind == "appliance":
            return done("handed-off", f"traffic to {dst} is sent to {route.target}, which decides what happens next")
        return done("left-vpc", f"traffic to {dst} leaves the VPC through {route.target} ({kind})")

    def _trace_inbound(self, destination: str) -> Trace:
        res = self.resources.get(destination)
        if res is None:
            raise ModelError(f"unknown destination '{destination}'")
        hops: list[Hop] = []
        igws = [g for g in self.gateways.values() if g.type == "internet"]
        if not igws:
            return Trace(INTERNET, destination, hops, "dropped", "the VPC has no internet gateway")
        if not res.public_ip:
            return Trace(INTERNET, destination, hops, "dropped",
                         f"{destination} has no public IPv4 address, so nothing on the internet can address it")
        hops.append(Hop(INTERNET, None, None, f"{igws[0].name} translates the public address to {res.ip}"))
        table = self.table_for(res.subnet)
        back = table.lookup(INTERNET_IP)
        hops.append(Hop(destination, table.name, back, "reply"))
        if back is None or self.gateway_type(back.target) != "internet":
            return Trace(INTERNET, destination, hops, "dropped",
                         f"{table.name} has no route back to an internet gateway, so the replies are dropped")
        return Trace(INTERNET, destination, hops, "delivered", f"{destination} is reachable from the internet")

    # ------------------------------------------------------------ audit
    def audit(self) -> list[Finding]:
        out: list[Finding] = []

        def add(sev, code, subject, message):
            out.append(Finding(sev, code, subject, message))

        for s in self.subnets.values():
            table = self.table_for(s.name)
            route = table.lookup(INTERNET_IP)
            kind = self.gateway_type(route.target) if route else None
            if s.internet == "none" and kind == "internet":
                add("critical", "isolated-subnet-routes-to-internet", s.name,
                    f"{s.name} should have no internet access, but {table.name} sends {route.destination} to "
                    f"{route.target}")
            elif s.internet == "none" and kind == "nat":
                add("high", "isolated-subnet-has-egress", s.name,
                    f"{s.name} should have no internet access, but {table.name} lets it send data out "
                    f"through {route.target}")
            if s.internet == "public" and kind != "internet":
                add("high", "public-subnet-without-internet-route", s.name,
                    f"{s.name} is internet-facing, but {table.name} has no route to an internet gateway")
            if s.internet == "outbound" and kind == "internet":
                add("high", "private-subnet-routes-to-internet-gateway", s.name,
                    f"{s.name} should only call out, but {table.name} sends internet traffic to {route.target}: "
                    "servers without a public address lose internet access, and any with one are exposed")
            if s.internet == "outbound" and kind not in ("nat", "internet", "transit", "appliance"):
                add("high", "no-outbound-route", s.name,
                    f"{s.name} needs to call out, but {table.name} has no working route to the internet")
            if kind == "nat":
                gw = self.gateways[route.target]
                if self.subnets[gw.subnet].az != s.az:
                    add("medium", "nat-in-other-az", s.name,
                        f"{s.name} ({s.az}) uses {gw.name} in {self.subnets[gw.subnet].az}: losing that zone "
                        "cuts this one off, and every byte pays cross-AZ charges")
        implicit = [s for s in self.subnets if self.is_implicit(s)]
        if implicit:
            add("low", "implicit-association", self.main_table.name,
                f"{', '.join(implicit)} {'has' if len(implicit) == 1 else 'have'} no explicit association, "
                f"so {'it follows' if len(implicit) == 1 else 'they follow'} whatever the main route table says")

        tiers: dict[str, set[str]] = {}
        for s in self.subnets.values():
            tiers.setdefault(self.table_for(s.name).name, set()).add(s.internet)
        for name, intents in tiers.items():
            if len(intents) > 1:
                add("medium", "route-table-shared-across-tiers", name,
                    f"{name} serves subnets with different internet needs ({', '.join(sorted(intents))}), "
                    "so one route can never suit them all")

        if any(self.gateway_type(r.target) == "internet" for r in self.main_table.routes):
            add("high", "main-table-routes-to-internet", self.main_table.name,
                f"the main route table {self.main_table.name} routes to an internet gateway, so any new subnet "
                "without an explicit association is public")

        for t in self.tables.values():
            for r in t.routes:
                kind = self.gateway_type(r.target)
                if kind is None:
                    add("high", "blackhole-route", t.name,
                        f"{t.name} sends {r.destination} to {r.target}, which does not exist (blackhole)")
                elif r.destination != self.cidr and r.destination.subnet_of(self.cidr):
                    add("info", "more-specific-than-local", t.name,
                        f"{t.name} diverts traffic for subnet {r.destination} to {r.target}; check the replies "
                        "come back the same way and the appliance is redundant")

        for g in self.gateways.values():
            if g.type == "nat" and not self.reaches_internet_gateway(g.subnet):
                add("high", "nat-gateway-without-internet-route", g.name,
                    f"{g.name} is in {g.subnet}, whose route table has no route to an internet gateway")

        exposed = set()
        for r in self.resources.values():
            subnet = self.subnets[r.subnet]
            if subnet.internet != "public" and self.trace(INTERNET, r.name).reachable:
                exposed.add(r.name)
                add("critical", "reachable-from-internet", r.name,
                    f"{r.name} in {r.subnet} has a public IPv4 address and a route to the internet gateway")
            elif subnet.internet != "public" and r.public_ip:
                add("medium", "public-ip-outside-public-tier", r.name,
                    f"{r.name} has a public IPv4 address in {r.subnet}: one route away from being exposed")

        for f in self.flows:
            want = f.get("expect", "reachable")
            t = self.trace(f["from"], f["to"])
            if want == "reachable" and t.outcome != "delivered":
                add("high", "flow-broken", f"{f['from']} -> {f['to']}", t.reason)
            elif want == "blocked" and t.reachable and not (f["from"] == INTERNET and f["to"] in exposed):
                add("critical", "flow-not-blocked", f"{f['from']} -> {f['to']}", t.reason)

        out.sort(key=lambda x: (SEVERITIES.index(x.severity), x.code, x.subject))
        return out


def load(path: str | Path) -> Vpc:
    with open(path, encoding="utf-8") as fh:
        return Vpc(json.load(fh))


# ---------------------------------------------------------------- command line
def cmd_tables(vpc: Vpc) -> int:
    for t in vpc.tables.values():
        subnets = [s for s in vpc.subnets if vpc.table_for(s).name == t.name]
        label = " (main)" if t.main else ""
        print(f"{t.name}{label}: {', '.join(subnets) or 'no subnets'}")
        for r in sorted(t.routes, key=lambda r: -r.destination.prefixlen):
            print(f"  {str(r.destination):<18} {r.target}")
    return 0


def cmd_trace(vpc: Vpc, path: list[str]) -> int:
    """Trace each leg of a path, e.g. internet -> load balancer -> web -> app -> database."""
    ok = True
    for source, destination in zip(path, path[1:]):
        t = vpc.trace(source, destination)
        ok = ok and t.outcome == "delivered"
        print(f"{source} -> {destination}: {t.outcome}")
        for hop in t.hops:
            print(f"  {hop}")
        print(f"  {t.reason}")
    return 0 if ok else 1


def cmd_audit(vpc: Vpc, name: str) -> int:
    findings = vpc.audit()
    counts = ", ".join(f"{sum(f.severity == s for f in findings)} {s}" for s in SEVERITIES
                       if any(f.severity == s for f in findings))
    print(f"{name}: {len(findings)} finding{'s' if len(findings) != 1 else ''}" + (f" ({counts})" if counts else ""))
    for f in findings:
        print(f"  {f.severity.upper():<8} {f.code:<42} {f.subject}")
        print(f"           {f.message}")
    return 1 if any(f.severity in ("critical", "high") for f in findings) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("tables", "audit"):
        sub.add_parser(cmd).add_argument("model")
    tr = sub.add_parser("trace")
    tr.add_argument("model")
    tr.add_argument("source", help="a resource name, or 'internet'")
    tr.add_argument("destination", nargs="+",
                    help="a resource name, an IP address or 'internet'; several trace a path leg by leg")
    args = parser.parse_args(argv)
    try:
        vpc = load(args.model)
        if args.command == "tables":
            return cmd_tables(vpc)
        if args.command == "trace":
            return cmd_trace(vpc, [args.source, *args.destination])
        return cmd_audit(vpc, Path(args.model).name)
    except (ModelError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
