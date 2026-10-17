---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Inspect all inbound traffic inline with a Gateway Load Balancer at the internet gateway

> In the context of a telemedicine platform whose compliance rule says every packet entering the platform must pass a third-party intrusion detection system before it reaches any component, facing a load balancer and media relays that would otherwise be the first things the traffic touches, we decided to route all traffic arriving at the internet gateway through Gateway Load Balancer endpoints to a fleet of third-party IDS appliances, and neglected mirroring traffic to an out-of-band IDS, AWS Network Firewall with partner rules, inspecting between the load balancer and the web tier, and a single appliance as the route target, to achieve inspection before anything in the VPC is reached, for every protocol, accepting an extra hop on every packet, appliance licences and a fleet to run.

## Context and Problem Statement

Doctors use the portal in a web browser and patients use a mobile app. Both reach the platform over HTTPS, and video consultations add audio and video over UDP to media relays. The compliance rule has two parts: medical records must never be directly reachable from the internet, and all traffic into the platform must be inspected by a third-party intrusion detection system before it reaches any component. "Any component" includes the Application Load Balancer and the media relays, because they are the first components the traffic meets inside the VPC. Where, and how, should the inspection happen?

## Decision Drivers

* Inspection before any component sees the traffic, for every protocol (HTTPS and UDP media), in both Availability Zones.
* A third-party intrusion detection system, as the rule says: a third-party engine, not only third-party rules.
* No single point of failure, and capacity that grows with the number of consultations.
* If inspection is down, traffic must stop rather than flow uninspected, which is the rule's intent.
* Symmetric paths: a reply must pass the same appliance as its request, or a stateful IDS sees only half of each conversation.

## Considered Options

* Gateway Load Balancer endpoints as the targets of the internet gateway's own route table (ingress routing)
* VPC Traffic Mirroring to an out-of-band IDS
* AWS Network Firewall with partner managed rules from AWS Marketplace
* An IDS layer between the Application Load Balancer and the web tier
* A single IDS instance as the target of the internet gateway's route table

## Decision Outcome

Chosen option: "Gateway Load Balancer endpoints as the targets of the internet gateway's own route table", because it is the only option that puts a third-party appliance in front of every component, for every protocol, without a single point of failure.

The internet gateway gets a route table of its own (an edge association). It sends traffic for each public subnet's CIDR to the Gateway Load Balancer endpoint in the same zone. The endpoint passes each packet over AWS PrivateLink to a Gateway Load Balancer in the inspection VPC ([ADR-0002](0002-run-the-ids-fleet-in-a-separate-inspection-vpc.md)), which hands it to a healthy appliance inside a GENEVE tunnel on UDP 6081 and keeps every packet of a flow on the same appliance. After inspection the packet comes back out of the same endpoint and continues to its destination. Each public subnet's route table sends `0.0.0.0/0` through its own zone's endpoint, so replies, and the NAT gateways' outbound traffic, are inspected on the same path. The appliances start in detection mode (alert only); the security team can turn on prevention for high-confidence signatures once the rules are tuned.

### Consequences

* Good, because nothing in the VPC sees a packet before an appliance has, whatever its protocol or port: a Gateway Load Balancer passes all IP traffic.
* Good, because the fleet scales out and each zone has its own endpoint, so losing one appliance, or one zone, does not stop inspection elsewhere.
* Good, because it fails closed: when every appliance is unhealthy, the Gateway Load Balancer drops the traffic instead of letting it through.
* Good, because outbound traffic through the NAT gateways is inspected by the same fleet, with no extra design.
* Bad, because HTTPS is still encrypted when the appliances see it. They detect at the network and TLS layers (scans, floods, known-bad sources, malformed handshakes), and attacks inside HTTP are left to AWS WAF on the load balancer. Seeing inside HTTPS would need inbound TLS decryption on the appliances, which means copying the portal's private key to them.
* Bad, because every packet takes an extra hop and pays Gateway Load Balancer, endpoint and data processing charges, on top of the appliance licences.
* Bad, because the team must patch, tune and watch a third-party fleet.

### Confirmation

* A test from outside AWS: a port scan of the load balancer and of a media relay raises an alert on an appliance.
* Stopping every appliance in one zone stops new connections in that zone (fail closed), while the other zone keeps serving.
* VPC Flow Logs on the public subnets show no accepted inbound flow that did not come through an endpoint.
* AWS Config checks that the gateway route table keeps its two routes, and that each public route table points `0.0.0.0/0` at its own zone's endpoint.

## Pros and Cons of the Options

### Gateway Load Balancer endpoints as the internet gateway's route targets

* Good, because traffic is inspected before any component, for any protocol.
* Good, because it scales, and survives the loss of an appliance or a zone.
* Bad, because of the cost and the fleet to run.

### VPC Traffic Mirroring to an out-of-band IDS

* Good, because it is simple and adds no hop to the live path.
* Bad, because it copies traffic from network interfaces that have already received it, so the components see every packet before the IDS does. It cannot meet "before reaching any component".
* Bad, because a copy can only raise alerts, never block anything.

### AWS Network Firewall with partner managed rules

* Good, because AWS manages and scales it, with no fleet to run. Since November 2025 it can run managed rule groups from AWS Partners such as Check Point, Fortinet and Trend Micro, sold in AWS Marketplace.
* Bad, because the inspection engine is still AWS's own; only the rules come from a third party. If the compliance team accepts third-party rules as a third-party IDS, this option is simpler and this record should be revisited.

### An IDS layer between the load balancer and the web tier

* Good, because the appliances could see decrypted HTTP, if the load balancer sends plain HTTP to its targets.
* Bad, because the load balancer and the media relays are reached before any inspection, which breaks the rule.

### A single IDS instance as the route target

* Good, because it is the cheapest way to put an appliance in the path.
* Bad, because it is a single point of failure that cannot scale: if it stops, the platform stops. Its network interface also needs a public IP address of its own.

## More Information

* Related: [ADR-0002](0002-run-the-ids-fleet-in-a-separate-inspection-vpc.md) and the [study write-up](../README.md).
* Sources: [Gateway route tables](https://docs.aws.amazon.com/vpc/latest/userguide/gateway-route-tables.html), [What is a Gateway Load Balancer?](https://docs.aws.amazon.com/elasticloadbalancing/latest/gateway/introduction.html), [Gateway Load Balancer target failure scenarios](https://docs.aws.amazon.com/elasticloadbalancing/latest/gateway/health-checks.html), [What is Traffic Mirroring?](https://docs.aws.amazon.com/vpc/latest/mirroring/what-is-traffic-mirroring.html) and [AWS Network Firewall managed rules from AWS Partners](https://aws.amazon.com/about-aws/whats-new/2025/11/network-firewall-managed-rules-partners-marketplace/).
* Confidence: high for where inspection sits; the choice of appliance belongs to the security team. Revisit if the compliance team accepts Network Firewall with partner rules.
