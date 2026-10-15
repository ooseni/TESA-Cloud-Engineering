#!/usr/bin/env python3
"""Check a VPC's security groups and network ACLs the way AWS applies them, before anything is built.

The VPC is described in JSON: subnets and their network ACLs, security groups, and the resources
that use them. The tool follows AWS's rules:
- a security group is stateful: if a request is allowed, its reply is allowed back automatically;
- a network ACL is stateless: the reply needs a rule of its own, on the client's ephemeral ports;
- network ACL rules are evaluated lowest number first, the first match decides, and the final
  `*` rule denies anything left over;
- network ACLs filter traffic entering and leaving a subnet, not traffic within one;
- a NAT gateway has no security group, but both network ACLs on its path apply.

It traces a TCP connection check by check, request then reply, and audits a design for the
misconfigurations that expose a bank's data or break its payments. Routing is module 05.

Examples:
    python filter_check.py tables examples/bank-filters.json
    python filter_check.py trace examples/bank-filters.json app-a db-a 5432
    python filter_check.py trace examples/bank-filters.json app-a internet 443
    python filter_check.py audit examples/as-found.json
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
ANYWHERE = ipaddress.ip_network("0.0.0.0/0")
ALL = (0, 65535)
# Ephemeral (client) ports by who opens the connection, from the Amazon VPC User Guide
CLIENT_PORTS = {
    "linux": (32768, 61000),
    "windows": (49152, 65535),
    "alb": (1024, 65535),
    "nat": (1024, 65535),
    "lambda": (1024, 65535),
    "internet": (1024, 65535),      # any client on the internet: the widest range AWS recommends
}
PROTOCOLS = ("tcp", "udp", "icmp", "all")
TIERS = ("public", "web", "app", "data")
SEVERITIES = ("critical", "high", "medium", "low", "info")
NACL_RULE_QUOTA = 20                # per direction, adjustable to 40

Network = ipaddress.IPv4Network
Address = ipaddress.IPv4Address


class ModelError(ValueError):
    """The JSON describes something AWS would refuse to create."""


def parse_ports(text) -> tuple[int, int]:
    text = str(text).strip().lower()
    if text in ("all", "-1", "0-65535"):
        return ALL
    lo, _, hi = text.partition("-")
    try:
        lo_i, hi_i = int(lo), int(hi or lo)
    except ValueError:
        raise ModelError(f"'{text}' is not a port or a port range") from None
    if not 0 <= lo_i <= hi_i <= 65535:
        raise ModelError(f"port range '{text}' is out of bounds")
    return lo_i, hi_i


def show_ports(ports: tuple[int, int]) -> str:
    if ports == ALL:
        return "all"
    return str(ports[0]) if ports[0] == ports[1] else f"{ports[0]}-{ports[1]}"


def _network(text: str, what: str) -> Network:
    try:
        net = ipaddress.ip_network(text, strict=True)
    except ValueError as exc:
        raise ModelError(f"{what}: '{text}' is not a valid IPv4 network ({exc})") from None
    if net.version != 4:
        raise ModelError(f"{what}: '{text}' is IPv6; this tool checks IPv4 rules")
    return net


# ---------------------------------------------------------------- security groups
@dataclass(frozen=True)
class SgRule:
    protocol: str
    ports: tuple[int, int]
    peer: str                        # a CIDR block or another security group's name

    def matches(self, protocol: str, port: int, peer_ip: Address, peer_sgs: tuple[str, ...]) -> bool:
        if self.protocol not in ("all", protocol):
            return False
        if not (self.protocol == "all" or self.ports[0] <= port <= self.ports[1]):
            return False
        if self.peer.startswith("sg-"):
            return self.peer in peer_sgs
        return peer_ip in ipaddress.ip_network(self.peer)

    def describe(self, direction: str) -> str:
        what = "all traffic" if self.protocol == "all" else f"{self.protocol.upper()} {show_ports(self.ports)}"
        return f"{what} {'from' if direction == 'inbound' else 'to'} {self.peer}"


@dataclass
class SecurityGroup:
    name: str
    inbound: list[SgRule]
    outbound: list[SgRule]


# ---------------------------------------------------------------- network ACLs
@dataclass(frozen=True)
class AclRule:
    number: int
    protocol: str
    ports: tuple[int, int]
    cidr: Network
    action: str
    why: str = field(default="", compare=False)

    def describe(self, direction: str) -> str:
        what = "all traffic" if self.protocol == "all" else f"{self.protocol.upper()} {show_ports(self.ports)}"
        return f"rule {self.number}: {what} {'from' if direction == 'inbound' else 'to'} {self.cidr}"


@dataclass
class Nacl:
    name: str
    inbound: list[AclRule]
    outbound: list[AclRule]

    def decide(self, direction: str, protocol: str, ports: tuple[int, int], peer_ip: Address):
        """First match wins, port by port: returns (allowed, rules that decided, ranges denied).

        A whole port range is checked because a reply can come back on any of the client's
        ephemeral ports, so a rule must cover all of them."""
        remaining = [ports]
        used: list[AclRule] = []
        denied: list[tuple[int, int]] = []
        for rule in getattr(self, direction):
            if rule.protocol not in ("all", protocol) or peer_ip not in rule.cidr:
                continue
            span = ALL if rule.protocol == "all" else rule.ports
            left, hit = [], False
            for lo, hi in remaining:
                a, b = max(lo, span[0]), min(hi, span[1])
                if a > b:
                    left.append((lo, hi))
                    continue
                hit = True
                if rule.action == "deny":
                    denied.append((a, b))
                if lo < a:
                    left.append((lo, a - 1))
                if b < hi:
                    left.append((b + 1, hi))
            if hit:
                used.append(rule)
            remaining = left
            if not remaining:
                break
        star = bool(remaining)                   # whatever is left reaches the * rule
        return not (denied or remaining), used, denied + remaining, star


def default_nacl() -> Nacl:
    """The VPC's default network ACL: everything allowed both ways (rule 100)."""
    rule = AclRule(100, "all", ALL, ANYWHERE, "allow")
    return Nacl("default", [rule], [rule])


# ---------------------------------------------------------------- the VPC
@dataclass(frozen=True)
class Subnet:
    name: str
    network: Network
    tier: str
    nacl: str
    nat: str | None = None


@dataclass(frozen=True)
class Resource:
    name: str
    subnet: str
    ip: Address
    sgs: tuple[str, ...]
    kind: str = "instance"
    os: str = "linux"

    @property
    def client_ports(self) -> tuple[int, int]:
        return CLIENT_PORTS.get(self.kind) or CLIENT_PORTS[self.os]


@dataclass(frozen=True)
class Check:
    phase: str          # request | reply
    layer: str          # sg-app, nacl-data, ...
    direction: str      # inbound | outbound
    detail: str
    allowed: bool
    kind: str           # sg | nacl

    def __str__(self) -> str:
        return f"{self.phase:<8} {self.layer:<12} {self.direction:<9} {'allow' if self.allowed else 'DENY ':<6} {self.detail}"


@dataclass
class Trace:
    source: str
    destination: str
    port: int
    checks: list[Check]

    @property
    def allowed(self) -> bool:
        return all(c.allowed for c in self.checks)

    @property
    def first_failure(self) -> Check | None:
        return next((c for c in self.checks if not c.allowed), None)

    @property
    def reason(self) -> str:
        bad = self.first_failure
        if bad is None:
            return f"{self.source} reaches {self.destination} on TCP {self.port}, and the replies get back"
        return f"blocked at {bad.layer} {bad.direction} ({bad.phase}): {bad.detail}"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    subject: str
    message: str


class Vpc:
    def __init__(self, data: dict):
        vpc = data.get("vpc", {})
        self.cidr = _network(vpc.get("cidr", ""), "VPC CIDR")

        self.nacls: dict[str, Nacl] = {"default": default_nacl()}
        for name, n in data.get("nacls", {}).items():
            self.nacls[name] = Nacl(name, self._acl_rules(name, n.get("inbound", [])),
                                    self._acl_rules(name, n.get("outbound", [])))

        self.subnets: dict[str, Subnet] = {}
        for name, s in data.get("subnets", {}).items():
            net = _network(s.get("cidr", ""), f"subnet {name}")
            if not net.subnet_of(self.cidr):
                raise ModelError(f"subnet {name} ({net}) is outside the VPC ({self.cidr})")
            if s.get("tier") not in TIERS:
                raise ModelError(f"subnet {name}: tier must be one of {', '.join(TIERS)}")
            nacl = s.get("nacl", "default")
            if nacl not in self.nacls:
                raise ModelError(f"subnet {name} uses unknown network ACL {nacl}")
            self.subnets[name] = Subnet(name, net, s["tier"], nacl, s.get("nat"))

        self.sgs: dict[str, SecurityGroup] = {}
        names = set(data.get("security_groups", {}))
        for name, g in data.get("security_groups", {}).items():
            if not name.startswith("sg-"):
                raise ModelError(f"security group {name}: name it sg-something, so rules can refer to it")
            self.sgs[name] = SecurityGroup(name, self._sg_rules(name, g.get("inbound", []), names),
                                           self._sg_rules(name, g.get("outbound", []), names))

        self.resources: dict[str, Resource] = {}
        for name, r in data.get("resources", {}).items():
            subnet = self.subnets.get(r.get("subnet"))
            if subnet is None:
                raise ModelError(f"resource {name} is in unknown subnet {r.get('subnet')}")
            ip = ipaddress.ip_address(r.get("ip", ""))
            net = subnet.network
            if ip not in net or ip in (net[0], net[1], net[2], net[3], net[-1]):
                raise ModelError(f"resource {name}: {ip} is not a usable address in {net}")
            kind = r.get("kind", "instance")
            sgs = tuple(r.get("security_groups", []))
            if kind == "nat" and sgs:
                raise ModelError(f"{name}: a NAT gateway has no security groups")
            if kind != "nat" and not sgs:
                raise ModelError(f"{name}: every {kind} has at least one security group")
            for g in sgs:
                if g not in self.sgs:
                    raise ModelError(f"{name} uses unknown security group {g}")
            self.resources[name] = Resource(name, subnet.name, ip, sgs, kind, r.get("os", "linux"))
        for s in self.subnets.values():
            if s.nat and (s.nat not in self.resources or self.resources[s.nat].kind != "nat"):
                raise ModelError(f"subnet {s.name}: nat must name a NAT gateway resource")
        self.flows = list(data.get("flows", []))

    def _acl_rules(self, nacl: str, rows: list) -> list[AclRule]:
        rules, seen = [], set()
        for row in rows:
            number = int(row["rule"])
            if not 1 <= number <= 32766:
                raise ModelError(f"{nacl}: rule numbers run from 1 to 32766, got {number}")
            if number in seen:
                raise ModelError(f"{nacl}: rule {number} appears twice in one direction")
            seen.add(number)
            protocol = row.get("protocol", "tcp").lower()
            if protocol not in PROTOCOLS:
                raise ModelError(f"{nacl} rule {number}: unknown protocol {protocol}")
            action = row.get("action", "allow").lower()
            if action not in ("allow", "deny"):
                raise ModelError(f"{nacl} rule {number}: action must be allow or deny")
            rules.append(AclRule(number, protocol, parse_ports(row.get("ports", "all")),
                                 _network(row.get("cidr", ""), f"{nacl} rule {number}"), action,
                                 row.get("why", "")))
        return sorted(rules, key=lambda r: r.number)

    def _sg_rules(self, sg: str, rows: list, names: set) -> list[SgRule]:
        rules = []
        for row in rows:
            protocol = row.get("protocol", "tcp").lower()
            if protocol not in PROTOCOLS:
                raise ModelError(f"{sg}: unknown protocol {protocol}")
            peer = row.get("peer", "")
            if peer.startswith("sg-"):
                if peer not in names:
                    raise ModelError(f"{sg} refers to unknown security group {peer}")
            else:
                _network(peer, f"{sg} rule")
            rules.append(SgRule(protocol, parse_ports(row.get("ports", "all")), peer))
        return rules

    # ------------------------------------------------------------ tracing
    def _sg_check(self, res: Resource, direction: str, port: int, peer_ip, peer_sgs, phase: str) -> Check:
        rules = [r for g in res.sgs for r in getattr(self.sgs[g], direction)]
        hit = next((r for r in rules if r.matches("tcp", port, peer_ip, peer_sgs)), None)
        label = "+".join(res.sgs)
        if hit:
            return Check(phase, label, direction, hit.describe(direction), True, "sg")
        return Check(phase, label, direction, f"no {direction} rule for TCP {port} "
                     f"{'from' if direction == 'inbound' else 'to'} {peer_ip}", False, "sg")

    def _acl_check(self, subnet: str, direction: str, ports: tuple[int, int], peer_ip, phase: str) -> Check:
        nacl = self.nacls[self.subnets[subnet].nacl]
        ok, used, denied, star = nacl.decide(direction, "tcp", ports, peer_ip)
        if ok:
            rules = "; ".join(r.describe(direction) for r in used)
            detail = rules if ports[0] == ports[1] else f"{rules} (covers {show_ports(ports)})"
        else:
            gaps = ", ".join(show_ports(d) for d in denied)
            blockers = [f"rule {r.number}" for r in used if r.action == "deny"] + (["the * rule"] if star else [])
            detail = (f"TCP {gaps} {'from' if direction == 'inbound' else 'to'} {peer_ip} "
                      f"is denied by {' and '.join(blockers)}")
        return Check(phase, nacl.name, direction, detail, ok, "nacl")

    def _stateful(self, res: Resource, direction: str) -> Check:
        return Check("reply", "+".join(res.sgs), direction,
                     "stateful: the reply to an allowed request is allowed", True, "sg")

    def endpoint(self, name: str):
        if name == INTERNET:
            return None
        if name not in self.resources:
            raise ModelError(f"unknown resource '{name}'")
        return self.resources[name]

    def trace(self, source: str, destination: str, port: int) -> Trace:
        src, dst = self.endpoint(source), self.endpoint(destination)
        checks: list[Check] = []
        if src is None and dst is None:
            raise ModelError("one end of the connection must be inside the VPC")

        def done(replies):
            if all(c.allowed for c in checks):           # replies only exist if the request arrived
                checks.extend(r() for r in replies)
            return Trace(source, destination, port, checks)

        if src is None:                                      # a client on the internet
            client = CLIENT_PORTS["internet"]
            checks.append(self._acl_check(dst.subnet, "inbound", (port, port), INTERNET_IP, "request"))
            checks.append(self._sg_check(dst, "inbound", port, INTERNET_IP, (), "request"))
            return done([lambda: self._stateful(dst, "outbound"),
                         lambda: self._acl_check(dst.subnet, "outbound", client, INTERNET_IP, "reply")])

        if dst is None:                                      # out to the internet
            checks.append(self._sg_check(src, "outbound", port, INTERNET_IP, (), "request"))
            checks.append(self._acl_check(src.subnet, "outbound", (port, port), INTERNET_IP, "request"))
            replies = []
            nat_name = self.subnets[src.subnet].nat
            if nat_name:                                     # through the NAT gateway's subnet and back
                nat = self.resources[nat_name]
                if nat.subnet != src.subnet:
                    checks.append(self._acl_check(nat.subnet, "inbound", (port, port), src.ip, "request"))
                checks.append(self._acl_check(nat.subnet, "outbound", (port, port), INTERNET_IP, "request"))
                replies.append(lambda: self._acl_check(nat.subnet, "inbound", nat.client_ports, INTERNET_IP, "reply"))
                if nat.subnet != src.subnet:
                    replies.append(lambda: self._acl_check(nat.subnet, "outbound", src.client_ports, src.ip, "reply"))
            replies.append(lambda: self._acl_check(src.subnet, "inbound", src.client_ports, INTERNET_IP, "reply"))
            replies.append(lambda: self._stateful(src, "inbound"))
            return done(replies)

        crossing = src.subnet != dst.subnet                  # network ACLs only see traffic between subnets
        checks.append(self._sg_check(src, "outbound", port, dst.ip, dst.sgs, "request"))
        if crossing:
            checks.append(self._acl_check(src.subnet, "outbound", (port, port), dst.ip, "request"))
            checks.append(self._acl_check(dst.subnet, "inbound", (port, port), src.ip, "request"))
        checks.append(self._sg_check(dst, "inbound", port, src.ip, src.sgs, "request"))
        replies = [lambda: self._stateful(dst, "outbound")]
        if crossing:
            replies.append(lambda: self._acl_check(dst.subnet, "outbound", src.client_ports, src.ip, "reply"))
            replies.append(lambda: self._acl_check(src.subnet, "inbound", src.client_ports, dst.ip, "reply"))
        replies.append(lambda: self._stateful(src, "inbound"))
        return done(replies)

    # ------------------------------------------------------------ audit
    def audit(self) -> list[Finding]:
        out: list[Finding] = []

        def add(sev, code, subject, message):
            out.append(Finding(sev, code, subject, message))

        tiers_of: dict[str, set[str]] = {}
        for r in self.resources.values():
            for g in r.sgs:
                tiers_of.setdefault(g, set()).add(self.subnets[r.subnet].tier)

        for g in self.sgs.values():
            tiers = tiers_of.get(g.name, set())
            for rule in g.inbound:
                anywhere = not rule.peer.startswith("sg-") and ipaddress.ip_network(rule.peer) == ANYWHERE
                every_port = rule.protocol == "all" or (rule.ports[0] <= 1 and rule.ports[1] == 65535)
                if anywhere and tiers - {"public"}:
                    sev = "critical" if "data" in tiers else "high"
                    add(sev, "sg-inbound-from-anywhere", g.name,
                        f"{g.name} admits {rule.describe('inbound')} on a {'/'.join(sorted(tiers - {'public'}))} "
                        "tier, which only its neighbouring tier should reach")
                elif anywhere and not every_port and not set(range(rule.ports[0], rule.ports[1] + 1)) <= {80, 443}:
                    add("high", "sg-admin-port-open", g.name,
                        f"{g.name} admits {rule.describe('inbound')} on the internet-facing tier; only 80 and 443 belong there")
                if every_port:
                    add("critical" if anywhere else "high", "sg-all-ports", g.name,
                        f"{g.name} admits {rule.describe('inbound')}: least privilege means one port per purpose")
            if "data" in tiers:
                for rule in g.outbound:
                    if not rule.peer.startswith("sg-") and ipaddress.ip_network(rule.peer) == ANYWHERE:
                        add("medium", "data-tier-egress", g.name,
                            f"{g.name} lets the database open connections to {rule.peer}: a ready path for "
                            "stolen data. A database needs no outbound rule to answer queries")

        for n in self.nacls.values():
            private = [s.name for s in self.subnets.values() if s.nacl == n.name and s.tier != "public"]
            if not private:
                continue
            for direction in ("inbound", "outbound"):
                if any(r.action == "allow" and r.protocol == "all" and r.cidr == ANYWHERE
                       for r in getattr(n, direction)):
                    add("medium", "nacl-allows-all", n.name,
                        f"{', '.join(private)} use {n.name}, which allows all {direction} traffic: no "
                        "subnet-level guardrail if a security group is wrong")
                    break
        for n in self.nacls.values():
            for direction in ("inbound", "outbound"):
                if len(getattr(n, direction)) > NACL_RULE_QUOTA:
                    add("info", "nacl-rule-quota", n.name,
                        f"{n.name} has {len(getattr(n, direction))} {direction} rules; the default quota is "
                        f"{NACL_RULE_QUOTA} (40 at most), so blocklists belong in AWS WAF or AWS Network Firewall")

        for f in self.flows:
            want = f.get("expect", "allowed")
            t = self.trace(f["from"], f["to"], int(f["port"]))
            subject = f"{f['from']} -> {f['to']} tcp/{f['port']}"
            bad = t.first_failure
            if want == "allowed" and bad:
                sg_ok = all(c.allowed for c in t.checks if c.kind == "sg")
                if bad.kind == "nacl" and bad.phase == "reply":
                    add("high", "nacl-missing-return-ports", subject, t.reason)
                elif bad.kind == "nacl" and sg_ok:
                    add("high", "nacl-blocks-what-sg-allows", subject, t.reason)
                else:
                    add("high", "flow-blocked", subject, t.reason)
            elif want == "blocked" and t.allowed:
                add("critical", "flow-not-blocked", subject, t.reason)

        out.sort(key=lambda x: (SEVERITIES.index(x.severity), x.code, x.subject))
        return out


def load(path: str | Path) -> Vpc:
    with open(path, encoding="utf-8") as fh:
        return Vpc(json.load(fh))


# ---------------------------------------------------------------- command line
def cmd_tables(vpc: Vpc) -> int:
    """Markdown tables of every security group and network ACL, ready for a README."""
    print("| Security group | Attached to | Inbound | Outbound |")
    print("|---|---|---|---|")
    for g in vpc.sgs.values():
        users = ", ".join(r.name for r in vpc.resources.values() if g.name in r.sgs) or "nothing"
        inbound = "; ".join(r.describe("inbound") for r in g.inbound) or "none"
        outbound = "; ".join(r.describe("outbound") for r in g.outbound) or "none"
        print(f"| `{g.name}` | {users} | {inbound} | {outbound} |")
    for n in vpc.nacls.values():
        subnets = [s.name for s in vpc.subnets.values() if s.nacl == n.name]
        if not subnets:
            continue
        print(f"\n**`{n.name}`** ({', '.join(subnets)})\n")
        print("| Rule | Direction | Protocol | Ports | Source or destination | Action | Purpose |")
        print("|---:|---|---|---|---|---|---|")
        for direction in ("inbound", "outbound"):
            for r in getattr(n, direction):
                proto = "All" if r.protocol == "all" else r.protocol.upper()
                print(f"| {r.number} | {direction.title()} | {proto} | {show_ports(r.ports).replace('all', 'All')} "
                      f"| `{r.cidr}` | {r.action.title()} | {r.why} |")
            print(f"| * | {direction.title()} | All | All | `0.0.0.0/0` | Deny | Everything else |")
    return 0


def cmd_trace(vpc: Vpc, source: str, destination: str, port: int) -> int:
    t = vpc.trace(source, destination, port)
    print(f"{source} -> {destination} tcp/{port}: {'allowed' if t.allowed else 'blocked'}")
    for c in t.checks:
        print(f"  {c}")
    print(f"  {t.reason}")
    return 0 if t.allowed else 1


def cmd_audit(vpc: Vpc, name: str) -> int:
    findings = vpc.audit()
    counts = ", ".join(f"{sum(f.severity == s for f in findings)} {s}" for s in SEVERITIES
                       if any(f.severity == s for f in findings))
    print(f"{name}: {len(findings)} finding{'s' if len(findings) != 1 else ''}" + (f" ({counts})" if counts else ""))
    for f in findings:
        print(f"  {f.severity.upper():<8} {f.code:<27} {f.subject}")
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
    tr.add_argument("destination", help="a resource name, or 'internet'")
    tr.add_argument("port", type=int, help="the destination TCP port")
    args = parser.parse_args(argv)
    try:
        vpc = load(args.model)
        if args.command == "tables":
            return cmd_tables(vpc)
        if args.command == "trace":
            return cmd_trace(vpc, args.source, args.destination, args.port)
        return cmd_audit(vpc, Path(args.model).name)
    except (ModelError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
