---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Scan platform A's outbound traffic with AWS Network Firewall

> In the context of platform A's outbound traffic, which must be scanned before it leaves the VPC, facing a rule that names no particular product and a small team, we decided to use AWS Network Firewall with an endpoint in each zone, and neglected third-party appliances behind a Gateway Load Balancer and a single scanning instance, to achieve managed, highly available scanning with stateful rules, accepting per-hour and per-gigabyte charges and AWS's rule engine rather than a vendor's.

## Context and Problem Statement

[ADR-0001](0001-select-platform-a-traffic-by-source-subnet.md) sends platform A's outbound traffic to a scanner; platform B's goes straight to the NAT gateway. The rule says only that the traffic is scanned. My original answer used one security appliance on an EC2 instance, in one zone. What should do the scanning?

## Decision Drivers

* No single point of failure: a scanner in each zone, and a zone failure must not stop the other zone's traffic.
* Scanning that understands traffic: known-bad destinations, malware and command-and-control signatures, and the domains platform A is allowed to call.
* Little to operate for a small team.
* Cost in proportion to platform A's traffic only.

## Considered Options

* AWS Network Firewall, one endpoint per zone
* Third-party appliances behind a Gateway Load Balancer
* A single scanning instance as the route target

## Decision Outcome

Chosen option: "AWS Network Firewall, one endpoint per zone", because it gives stateful scanning in every zone with nothing to patch or scale, and only platform A's traffic is routed to it.

The firewall has an endpoint in a dedicated subnet in each zone (`10.60.4.0/28`, `10.60.4.16/28`), with no workloads in those subnets, because an endpoint cannot filter traffic for its own subnet. Its policy uses stateful rule groups in strict order: AWS managed threat signature rule groups, a domain list of the services platform A is allowed to call (matched on the HTTP Host header and the TLS server name), and a default action that drops and logs everything else. Alert and flow logs go to Amazon CloudWatch Logs. TLS inspection, which would let the firewall see inside platform A's HTTPS, is left for the security team to decide, because it needs a certificate authority that platform A's servers trust.

### Consequences

* Good, because AWS runs, patches and scales the firewall, up to 100 Gbps in each zone.
* Good, because each zone has its own endpoint, so losing one zone leaves the other zone's scanning working.
* Good, because only platform A's traffic is routed to it, so only platform A's traffic is charged for it.
* Bad, because each endpoint is charged by the hour and by the gigabyte.
* Bad, because without TLS inspection the firewall sees the destination's name but not the content of HTTPS.
* Bad, because the engine is AWS's own. If the company later requires a particular vendor, ADR-0002 is superseded by third-party appliances behind a Gateway Load Balancer, on the same routes.

### Confirmation

* From a platform A server, a request to a domain outside the allow list is dropped and logged; a request to an allowed domain succeeds.
* A test signature request from platform A raises an alert in the firewall's alert log.
* From a platform B server, the same requests succeed and appear in no firewall log.

## Pros and Cons of the Options

### AWS Network Firewall

* Good, because it is managed, highly available in each zone and stateful.
* Good, because domain lists, threat signatures and logging are built in.
* Bad, because of the endpoint charges, and an engine the company did not choose by name.

### Third-party appliances behind a Gateway Load Balancer

* Good, because the company could pick a vendor and its threat intelligence.
* Bad, because there is a fleet to license, patch and scale, which is more than the rule asks for.

### A single scanning instance

* Good, because it is the cheapest to start with.
* Bad, because it is a single point of failure in one zone, cannot scale, and needs source and destination checking turned off. This is what my original answer used.

## More Information

* Related: [ADR-0001](0001-select-platform-a-traffic-by-source-subnet.md), [ADR-0003](0003-put-the-firewall-before-the-nat-gateway.md) and the [study write-up](../README.md).
* Sources: [VPC subnet configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-subnets.html), [VPC route table configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-route-tables.html) and [Example routing options: appliance considerations](https://docs.aws.amazon.com/vpc/latest/userguide/route-table-options.html#appliance-considerations).
* Confidence: high. Revisit if the company names a scanning vendor.
