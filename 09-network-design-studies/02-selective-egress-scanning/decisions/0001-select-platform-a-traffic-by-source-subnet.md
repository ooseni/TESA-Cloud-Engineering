---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Select platform A's outbound traffic by source subnet

> In the context of two platforms that share one application tier, where only platform A's outbound traffic may be scanned and platform B's must bypass the scanner, facing route tables that choose a path by destination only and cannot see which platform sent a packet, we decided to run each platform's application servers in subnets of their own, so that each subnet's route table decides the path, and neglected routing by destination, scanning everything with pass rules for platform B, and a forward proxy set in platform A's code, to achieve a selection that applications cannot bypass, accepting more subnets and two server groups where there was one.

## Context and Problem Statement

A technology company runs two platforms, A and B, behind one web tier. Both use a shared application layer and a database. The company's rule: outbound traffic from the application servers for platform A must be scanned before it leaves the VPC, and platform B's must not pass the scanner. A VPC route table picks a route by the packet's destination, never its source, so if both platforms' processes ran on the same servers in the same subnets, their traffic to the internet would match the same `0.0.0.0/0` route. How can the network tell the two platforms' traffic apart?

## Decision Drivers

* Only platform A's traffic is scanned; platform B's never reaches the scanner.
* The selection must hold even if an application is misconfigured or compromised.
* Platforms keep calling destinations that change over time, without network changes.
* Simple to operate, and the web and application tiers stay in separate subnets.

## Considered Options

* Separate application subnets for each platform, each with its own route table
* Route by destination: send platform A's known destinations to the scanner through prefix lists
* Scan everything, and let platform B's traffic through with pass rules
* A forward proxy configured only in platform A's applications

## Decision Outcome

Chosen option: "Separate application subnets for each platform", because a subnet's route table is the one thing that reliably separates the platforms, and no application can change it.

The shared application layer becomes two Auto Scaling groups: platform A's servers in `10.60.20.0/24` and `10.60.21.0/24`, platform B's in `10.60.30.0/24` and `10.60.31.0/24`. Platform A's route tables send `0.0.0.0/0` to the firewall endpoint in their zone; platform B's send it straight to the NAT gateway. Both still talk to the web tier and the database over the local route. The tier stays shared in role and code; only where each platform's servers run is split.

### Consequences

* Good, because the selection is made by the network: a process on a platform A server cannot reach the internet without passing the scanner, whatever its configuration.
* Good, because each platform scales, patches and is filtered on its own, and a fault on one platform's servers no longer touches the other's.
* Good, because new destinations need no network change.
* Bad, because there are four application subnets and two Auto Scaling groups instead of two and one.
* Bad, because if the two platforms ever ran in the same process, that process would have to move to platform A's servers and be scanned.

### Confirmation

* VPC Reachability Analyzer shows the path from a platform A server to an internet address passing the firewall endpoint, and the path from a platform B server reaching the NAT gateway directly.
* The firewall's flow logs contain source addresses from `10.60.20.0/23` only.
* AWS Config checks that platform B's route tables have no route to a firewall endpoint and platform A's have no route that bypasses it.

## Pros and Cons of the Options

### Separate application subnets for each platform

* Good, because route tables enforce it and applications cannot bypass it.
* Bad, because of the extra subnets and server groups.

### Route by destination

* Good, because the servers could stay shared.
* Bad, because it only works while platform A's destinations are known, fixed and never shared with platform B. A destination both platforms call would be scanned for both, or for neither.
* Bad, because every new destination, and every address change at a destination, needs a route change.

### Scan everything, with pass rules for platform B

* Good, because it is one simple path for all traffic.
* Bad, because platform B's traffic still passes the scanner, which is what the rule forbids, and platform B pays the scanner's charges.

### A forward proxy in platform A's applications

* Good, because it needs no routing changes.
* Bad, because it depends on every application honouring its proxy setting. Traffic that ignores the setting, or is not HTTP, leaves unscanned.

## More Information

* Related: [ADR-0002](0002-scan-with-aws-network-firewall.md), [ADR-0003](0003-put-the-firewall-before-the-nat-gateway.md) and the [study write-up](../README.md).
* Sources: [How route priority works](https://docs.aws.amazon.com/vpc/latest/userguide/route-tables-priority.html), [Example routing options](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-options.html) and [VPC Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html).
* Confidence: high. Revisit if the two platforms must run in one process.
