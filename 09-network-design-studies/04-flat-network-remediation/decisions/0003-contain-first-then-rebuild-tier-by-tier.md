---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Contain first, then rebuild in new subnets of the same VPC, tier by tier

> In the context of a live payments platform that has just been breached, facing an attacker who may still have access and customers who need payments to keep working, we decided to contain the breach within hours using only security group and address changes, then build the segmented tiers in new subnets of the same VPC and move traffic over gradually, and neglected building a new VPC and patching the flat network in place, to achieve a stop to the immediate exposure without an outage and a rebuild that can be rolled back at every step, accepting a few weeks in which old and new run side by side.

## Context and Problem Statement

An attacker exploited a web server and reached the application tier. No critical data was taken, but the database is still probed from the internet, the network is still flat, and the attacker may still be inside. ADR-0001 and ADR-0002 describe the target. How does the platform get there without an outage, and without leaving the door open while it does?

## Decision Drivers

* Close the known exposure within hours, not weeks.
* Keep evidence for the investigation.
* No payment outage; every step reversible.
* Keep what partners already trust, such as allowlisted addresses, where possible.

## Considered Options

* Contain now, then rebuild in new subnets of the same VPC and cut over gradually
* Build a new VPC and switch everything over to it
* Patch the flat network in place

## Decision Outcome

Chosen option: "Contain now, then rebuild in new subnets of the same VPC", because containment needs no rebuild, and the same VPC keeps its internet gateway, address range and the proxy's Elastic IP address, while new subnets let the old and new tiers run side by side.

**Containment, first 24 hours:**

1. Remove the database server's public address and restrict its security group to the application servers on the database port. The probing stops.
2. Replace the broad rules inside the flat subnet with tier-to-tier rules by security group reference: security groups apply per instance, so this works before anything moves.
3. Isolate the exploited web server with a security group that has no rules, snapshot its volumes for the investigation, and replace it with a server built from a patched image.
4. Rotate every credential the application tier held: database passwords, API keys and access keys.
5. Turn on Amazon GuardDuty, VPC Flow Logs, AWS CloudTrail and Amazon Inspector, and patch every server Inspector flags.

**Rebuild, over the following weeks:** create the new subnets beside the old one (the `/16` has room: the flat subnet uses only `10.80.0.0/24`), the firewall endpoints and the NAT gateways, moving the proxy's Elastic IP address to one of them. Replicate the database into Amazon RDS with AWS Database Migration Service, keeping it in sync. Launch the web and application tiers from patched images behind the new load balancer, shift customer traffic by weighted DNS from 10% to 100%, cut the database over, then stop the proxy and the old servers, keep their snapshots, and delete the flat subnet.

### Consequences

* Good, because the database stops being reachable from the internet on day one, before any rebuild.
* Good, because every rebuild step can be rolled back by shifting DNS weight back to the old servers.
* Good, because evidence is kept, and every credential the attacker could have seen is replaced.
* Bad, because old and new environments run, and cost, at the same time for a few weeks.
* Bad, because database replication needs care at cutover: a short write freeze while the last changes are applied.

### Confirmation

* After containment, a scan from the internet finds no open port on any server but the proxy's.
* GuardDuty and Inspector are enabled in the account, with no unresolved high-severity finding before cutover.
* AWS DMS validation reports the source and target tables in sync before the database cutover.
* After the flat subnet is deleted, VPC Reachability Analyzer finds no path from the internet gateway to any web, application or data server.

## Pros and Cons of the Options

### Contain now, rebuild in the same VPC

* Good, because the urgent exposure closes immediately and the rebuild is gradual and reversible.
* Bad, because of a few weeks of running both.

### A new VPC

* Good, because it starts clean, with no old rules or routes to forget.
* Bad, because new IDs, a new internet gateway and new addresses ripple into DNS, partner allowlists and monitoring, and the cutover risk is the same.

### Patch the flat network in place

* Good, because it is the least work.
* Bad, because the database keeps a route to the internet, the proxy stays a single point of failure, and everything stays in one zone.

## More Information

* Related: [ADR-0001](0001-replace-the-proxy-instance-with-managed-services.md), [ADR-0002](0002-segment-the-tiers-and-chain-security-groups.md) and the [study write-up](../README.md).
* Sources: [AWS Security Incident Response Guide](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/aws-security-incident-response-guide.html), [Amazon GuardDuty](https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html), [Amazon Inspector](https://docs.aws.amazon.com/inspector/latest/user/what-is-inspector.html) and [AWS Database Migration Service](https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html).
* Confidence: high for the order; the timings depend on the size of the database and the team.
