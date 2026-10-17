---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Put the firewall before the NAT gateway, with a route back through it

> In the context of platform A's outbound traffic being scanned by a stateful firewall (ADR-0002), facing a NAT gateway shared by both platforms and replies that, by default, return from the NAT gateway straight to the servers, we decided to place the firewall endpoints between platform A's subnets and the NAT gateway, and to give the NAT gateway's subnet a route that sends replies for platform A's subnet back through the same endpoint, and neglected placing the firewall after the NAT gateway and placing it before without a return route, to achieve symmetric scanning of platform A only, accepting one more route per zone that must never be removed.

## Context and Problem Statement

Platform A's servers send `0.0.0.0/0` to a firewall endpoint, and the endpoint's subnet sends it on to the NAT gateway. The NAT gateway replaces the source address with its own Elastic IP address, for both platforms, so after the NAT gateway the two platforms look the same. Replies come back to the NAT gateway, which sends them to the server using its own subnet's route table, whose `local` route reaches platform A's subnet directly. AWS documents that Network Firewall does not support asymmetric routing: a request and its reply must pass the same firewall endpoint, or its stateful features stop working. My original answer had exactly this gap. Where should the firewall sit, and how do the replies come back through it?

## Decision Drivers

* Scan platform A's traffic only.
* Every request and its reply pass the same firewall endpoint, in both zones.
* No extra NAT gateways.

## Considered Options

* Firewall before the NAT gateway, with a route for platform A's subnet back through the firewall in the NAT subnet's route table
* Firewall after the NAT gateway, between it and the internet gateway
* Firewall before the NAT gateway, with no return route

## Decision Outcome

Chosen option: "Firewall before the NAT gateway, with a return route", because it is the only placement where the firewall can still tell the platforms apart by source address, and the return route makes the path symmetric.

In each zone, three route tables carry platform A's traffic: `rt-platform-a-a` sends `0.0.0.0/0` to `vpce-fw-a`; `rt-firewall-a` sends `0.0.0.0/0` to `nat-a`; and `rt-public-a` sends `0.0.0.0/0` to the internet gateway and, more specifically, `10.60.20.0/24` to `vpce-fw-a`. A subnet route table may hold a route to another subnet's whole CIDR with a Network Firewall endpoint as its target, and the longest match wins over `local`. Zone b mirrors this with `10.60.21.0/24` and `vpce-fw-b`. Platform B's subnets are not named in any public route, so their replies return directly.

### Consequences

* Good, because the firewall sees platform A's real source addresses, so its rules and logs name the server that made each call.
* Good, because requests and replies pass the same endpoint, so stateful rules, signatures and domain filtering work.
* Good, because one NAT gateway per zone still serves both platforms.
* Bad, because the return route is easy to miss: removing it, or adding a platform A subnet without one, silently breaks scanning for that subnet.
* Bad, because each zone's public route table has to name each platform A subnet in that zone.

### Confirmation

* AWS Config, or a reviewed Terraform plan, checks that each public route table has a route for its zone's platform A subnet to its zone's firewall endpoint.
* VPC Reachability Analyzer traces both directions between a platform A server and an internet address, and both pass the same endpoint.
* The firewall's flow log shows established flows from platform A with replies counted, not only requests.

## Pros and Cons of the Options

### Before the NAT gateway, with a return route

* Good, because it scans platform A only, symmetrically, with real source addresses.
* Bad, because the return route must be kept in step with platform A's subnets.

### After the NAT gateway

* Good, because one route in each direction covers the whole VPC: the NAT subnet sends `0.0.0.0/0` to the firewall, and the internet gateway's route table sends the NAT subnet back to it.
* Bad, because after the NAT gateway both platforms share one address, so the firewall would scan platform B as well, which the rule forbids. Separating them would need a NAT gateway per platform in each zone.

### Before the NAT gateway, without a return route

* Good, because it is the fewest routes.
* Bad, because replies skip the firewall. AWS does not support asymmetric routing through Network Firewall, and its stateful inspection cannot work on half of each conversation. This was the flaw in my original answer.

## More Information

* Related: [ADR-0001](0001-select-platform-a-traffic-by-source-subnet.md), [ADR-0002](0002-scan-with-aws-network-firewall.md) and the [study write-up](../README.md).
* Sources: [Avoiding asymmetric routing with AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/asymmetric-routing.html), [Example routing options: routing for a middlebox appliance](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-options.html#route-tables-appliance-routing) and [Architecture with an internet gateway and a NAT gateway](https://docs.aws.amazon.com/network-firewall/latest/developerguide/arch-igw-ngw.html).
* Confidence: high.
