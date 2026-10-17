---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Replace the proxy instance with managed services, inspected by AWS Network Firewall

> In the context of a payments platform whose single proxy instance carried all inbound and outbound internet traffic, facing an overloaded proxy with little visibility that was also a single point of failure, we decided to replace it with an Application Load Balancer and AWS WAF for inbound traffic, NAT gateways for outbound traffic, and AWS Network Firewall endpoints between the internet gateway and the public subnets in each zone, and neglected scaling the proxy into a fleet, a larger proxy instance, and the load balancer and NAT gateways without a firewall, to achieve no single instance in the path and a log of every connection in both directions, accepting the charges of managed services and a new outbound address for partners to allowlist.

## Context and Problem Statement

The platform's engineers put one proxy server on Amazon EC2 to handle all traffic between the internet and the platform, in both directions. Within a month it was overloaded, the security team could see little of what passed through it, and if it stopped, so did the platform. The proxy's purpose, one controlled and observable point for internet traffic, was sound; its form was not. What should replace it?

## Decision Drivers

* No single instance whose failure stops payments.
* Capacity that follows traffic without manual resizing.
* Visibility: every connection in and out logged, with alerts on known threats.
* Less to operate than the proxy, not more.

## Considered Options

* An Application Load Balancer with AWS WAF in, NAT gateways out, and Network Firewall endpoints in front of both
* A fleet of proxy instances behind a Network Load Balancer, in two zones
* A larger proxy instance
* The load balancer and NAT gateways without a firewall

## Decision Outcome

Chosen option: "An Application Load Balancer with AWS WAF in, NAT gateways out, and Network Firewall endpoints in front of both", because each part is managed, highly available and scales on its own, and the firewall keeps the one thing the proxy was meant to give: a controlled, logged point for everything that crosses the internet edge.

The internet gateway gets its own route table, which sends each public subnet's traffic to the firewall endpoint in that zone; each public subnet sends `0.0.0.0/0` back through the same endpoint, so both directions pass it. The firewall subnets send `0.0.0.0/0` to the internet gateway. The load balancer, with AWS WAF managed rule groups and rate-based rules, is the only way in. Each zone's NAT gateway is the way out for that zone's servers; the proxy's Elastic IP address moves to one of them, so partners that allowlisted it keep working, and partners add the second. The firewall policy alerts and drops on AWS managed threat signatures and allows outbound connections only to the payment processor and the update repositories, by host name. Alert and flow logs go to Amazon CloudWatch Logs.

### Consequences

* Good, because no single instance carries the traffic: the load balancer, NAT gateways and firewall endpoints are all managed and present in both zones.
* Good, because inbound and outbound connections are both logged at the edge, and WAF logs show the HTTP layer.
* Good, because capacity scales without anyone resizing a server.
* Bad, because the load balancer, NAT gateways and firewall endpoints are each charged by the hour and by data processed.
* Bad, because partners must allowlist a second outbound address.
* Bad, because the firewall sees HTTPS encrypted: it inspects names, addresses and known threat patterns, while WAF handles attacks inside HTTP.

### Confirmation

* Stopping a whole zone's servers leaves payments flowing through the other zone.
* Firewall flow logs show every inbound connection to the load balancer and every outbound connection from the NAT gateways.
* An outbound request to a host name outside the allow list is dropped and logged.

## Pros and Cons of the Options

### Managed services with Network Firewall

* Good, because nothing in the path is a single instance, and every connection is logged.
* Bad, because of the managed-service charges.

### A fleet of proxies behind a Network Load Balancer

* Good, because it removes the single point of failure and keeps the proxy software the team knows.
* Bad, because the team still patches, scales and monitors proxy instances, the work that failed the first time.

### A larger proxy instance

* Good, because it is a one-line change.
* Bad, because it is still one instance: it delays the overload and keeps the single point of failure and the blind spot.

### The load balancer and NAT gateways without a firewall

* Good, because it is cheaper and simpler.
* Bad, because nothing would record or filter what crosses the edge, which is exactly the visibility the security team lacked.

## More Information

* Related: [ADR-0002](0002-segment-the-tiers-and-chain-security-groups.md), [ADR-0003](0003-contain-first-then-rebuild-tier-by-tier.md) and the [study write-up](../README.md).
* Sources: [Gateway route tables](https://docs.aws.amazon.com/vpc/latest/userguide/gateway-route-tables.html), [VPC route table configuration for AWS Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/vpc-config-route-tables.html), [NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html) and [AWS WAF managed rule groups](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups.html).
* Confidence: high.
