---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Allow outbound traffic only to the partner's API, with AWS Network Firewall

> In the context of a wallet service that needs the internet for one thing, the partner's API, facing the risk that a compromised server uses that same route to send data anywhere, we decided to route the wallet service's outbound traffic through AWS Network Firewall, which allows only the partner's API host name and address ranges and drops the rest, and to give the web and data tiers no route out at all, and neglected security group rules alone, Route 53 Resolver DNS Firewall alone and a forward proxy, to achieve an internet path that leads only to the partner, accepting firewall charges and rules to update when the partner changes its endpoints.

## Context and Problem Statement

[ADR-0001](0001-call-the-partner-with-mutual-tls-from-fixed-addresses.md) gives the wallet service a route to the internet through a NAT gateway. A route to the internet is a route to everywhere: if a wallet server were compromised, the same route could carry customer data to an attacker. The bank wants the internet path to lead to the partner and nowhere else, with every attempt to go elsewhere logged. How should outbound traffic be restricted?

## Decision Drivers

* Only the wallet service reaches the internet, and only the partner's API.
* Rules that follow the partner's host name, because its addresses may change.
* A record of every blocked attempt.
* The same behaviour in both zones.

## Considered Options

* AWS Network Firewall: allow the partner's host name and address ranges, drop everything else
* Security group rules that allow only the partner's address ranges
* Route 53 Resolver DNS Firewall alone
* A forward proxy on Amazon EC2

## Decision Outcome

Chosen option: "AWS Network Firewall", because it can match the partner's host name, add an address check, drop everything else and log it, in both zones, with nothing to patch.

The wallet subnets send `0.0.0.0/0` to the firewall endpoint in their zone, the firewall subnet sends it to the NAT gateway, and each public route table sends the wallet subnet's replies back through the same endpoint: the pattern from study 2's [ADR-0003](../../02-selective-egress-scanning/decisions/0003-put-the-firewall-before-the-nat-gateway.md). The firewall policy uses strict order:

1. Pass TLS on port 443 whose server name is the partner's API host.
2. If the partner publishes its address ranges, require the destination to be in them as well. Network Firewall matches host names from the TLS server name, not from the destination address, so a compromised server could send a forged name to another address; the address check closes that.
3. AWS managed threat signature rule groups.
4. Drop and alert everything else.

The web and data subnets have no route out of the VPC, so the firewall is not their only barrier. Security groups still allow the wallet service only 443 outbound.

### Consequences

* Good, because the one internet route leads only to the partner, and every attempt to go elsewhere is logged with the server's own address.
* Good, because the rules follow the partner's host name, with the address check as a second key.
* Good, because the firewall runs in each zone and AWS scales it.
* Bad, because each firewall endpoint is charged by the hour and by the gigabyte.
* Bad, because a new partner host name or address range needs a rule change before it works.

### Confirmation

* From a wallet server, a request to any other domain is dropped and appears in the firewall's alert log.
* A request with the partner's host name sent to an address outside the partner's ranges is dropped.
* From a web or data server, any attempt to reach the internet fails: there is no route.

## Pros and Cons of the Options

### AWS Network Firewall

* Good, because it filters by host name and address, statefully, with logs.
* Bad, because of the endpoint charges.

### Security group rules for the partner's address ranges

* Good, because they cost nothing and sit on the server itself.
* Bad, because security groups match addresses only, not names, and a partner behind a content delivery network may change addresses without notice. They are kept as a second layer (443 out only), not the main control.

### Route 53 Resolver DNS Firewall alone

* Good, because it blocks lookups of any domain but the partner's, cheaply.
* Bad, because it filters names, not connections: a server that connects straight to an address skips it. It belongs beside the firewall, not instead of it.

### A forward proxy on Amazon EC2

* Good, because it can log full requests and filter by URL.
* Bad, because it is a fleet to run and patch, and applications must be configured to use it.

## More Information

* Related: [ADR-0001](0001-call-the-partner-with-mutual-tls-from-fixed-addresses.md) and the [study write-up](../README.md).
* Sources: [Stateful domain list rule groups in AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/stateful-rule-groups-domain-names.html), [Avoiding asymmetric routing with AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/asymmetric-routing.html) and [Route 53 Resolver DNS Firewall](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall.html).
* Confidence: high.
