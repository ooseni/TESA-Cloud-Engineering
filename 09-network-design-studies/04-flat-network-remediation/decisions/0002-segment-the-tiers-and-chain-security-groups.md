---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Segment the tiers into subnets in two zones, and chain security groups

> In the context of web, application and database servers that shared one subnet routed to the internet, facing an attacker who moved from a web server to the application tier and a database probed from the internet, we decided to give each tier its own subnets in two Availability Zones and to let each tier reach only the next one, on one port, by security group reference, and neglected security groups alone inside the flat subnet and a VPC per tier, to achieve a network in which a compromised web server can reach one port on the application tier and nothing else, accepting more subnets and route tables to manage.

## Context and Problem Statement

Every server was in one subnet whose route table sent `0.0.0.0/0` to the internet gateway, so any server with a public address was on the internet; the database had one, and its port was open. Security groups allowed broad traffic inside the subnet, so an attacker on a web server could reach the application servers on any port. Everything ran in one Availability Zone. How should the network be divided so that one compromised tier cannot reach the others?

## Decision Drivers

* The database cannot be reached from the internet, by any route, whatever its address or rules.
* A compromised web server reaches only what web servers legitimately need: one port on the application tier.
* Two layers, so that one mistaken rule does not reopen a path.
* Two Availability Zones, so that one zone's failure does not stop payments.

## Considered Options

* A subnet for each tier in each of two zones, with security groups chained by reference and a network ACL on the data tier
* Security groups alone, inside the existing flat subnet
* A separate VPC for each tier

## Decision Outcome

Chosen option: "A subnet for each tier in each of two zones, with chained security groups", because only the subnets' route tables can take the database off the internet entirely, and only security groups can limit traffic between tiers to one port.

The tiers are: firewall endpoints, public (load balancer and NAT gateways), web, application and data, each with a subnet in eu-west-1a and eu-west-1b. The data subnets' route table has only the local route. A VPC's local route connects every subnet to every other, so subnets alone do not stop lateral movement; the security groups do. `sg-web` admits 443 only from `sg-alb`, `sg-app` admits 8080 only from `sg-web`, and `sg-db` admits 5432 only from `sg-app`, each by security group reference, with no other inbound rules. A network ACL on the data subnets repeats the database rule at the subnet boundary. The database moves to Amazon RDS Multi-AZ with "Publicly accessible" set to No.

### Consequences

* Good, because the database has no route to or from the internet, and four independent settings would have to fail together to expose it.
* Good, because a compromised web server can reach one port on the application tier, and a compromised application server one port on the database.
* Good, because two zones keep payments running if one fails.
* Bad, because there are ten subnets, five kinds of route table and a network ACL to manage, which needs infrastructure as code to stay correct.

### Confirmation

* VPC Reachability Analyzer finds no path from the internet gateway to the data subnets, and no path from the web subnets to the data subnets.
* AWS Config checks that no security group allows inbound traffic from `0.0.0.0/0` except `sg-alb`, and the rule `rds-instance-public-access-check` reports the database as not public.
* A penetration test from a web server reaches the application tier on 8080 only.

## Pros and Cons of the Options

### A subnet per tier, in two zones, with chained security groups

* Good, because routes and security groups each do the part only they can do.
* Bad, because of the number of subnets and tables to keep consistent.

### Security groups alone in the flat subnet

* Good, because it is fast: no server moves. It is the right first step during containment (ADR-0003).
* Bad, because every server keeps a route to the internet gateway, so one public address and one loose rule expose it again; and it stays in one zone with one network ACL for everything.

### A VPC per tier

* Good, because the separation is as strong as it gets.
* Bad, because the tiers would talk through peering or a transit gateway, with extra cost, latency and routing to manage, for no protection that subnets and security groups do not already give.

## More Information

* Related: [ADR-0001](0001-replace-the-proxy-instance-with-managed-services.md), [ADR-0003](0003-contain-first-then-rebuild-tier-by-tier.md) and the [study write-up](../README.md).
* Sources: [Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html), [Control subnet traffic with network access control lists](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html), [VPC Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html) and the [AWS Config rule rds-instance-public-access-check](https://docs.aws.amazon.com/config/latest/developerguide/rds-instance-public-access-check.html).
* Confidence: high.
