---
status: "accepted"
date: 2026-10-15
decision-makers: Oseni Sakariyau
---

# Use one public cloud, AWS, alongside the bank's data centres

> In the context of a bank serving Nigerian and EU customers from its own data centres, facing a board demand to cut infrastructure cost by 20% and a fragmented identity estate, we decided for one public cloud (AWS) alongside the data centres and neglected a second public cloud (Azure) and a private-cloud-only design, to achieve one identity plane, one network path and no cross-cloud data transfer charges, accepting that the bank depends on a single cloud provider.

## Context and Problem Statement

My original recommendation put EU customer data and the partner API gateway on Azure, and AI training and audit logs on AWS, beside the bank's data centres. That meant two public clouds, each with its own identity system (Microsoft Entra ID and AWS IAM) on top of the bank's directory, two sets of private links from the data centres, two skill sets, and charges for any data moved between clouds. Which public-cloud footprint meets every constraint at the lowest cost and risk?

## Decision Drivers

* The board's demand to cut infrastructure cost by 20%.
* Security: one source of identities and one set of access policies to audit.
* Operations: one toolchain (Terraform, monitoring, incident response) and one skill set to run it.
* Residency: EU personal data must stay in the EU, and Nigerian personal data in Nigeria (see [ADR-0002](0002-keep-nigerian-data-in-nigeria.md)).
* Elastic GPU capacity for AI training, including on data that may not leave Nigeria.

## Considered Options

* One public cloud (AWS) alongside the data centres
* Two public clouds (Azure for EU workloads, AWS for AI and audit) alongside the data centres
* Private cloud only (the data centres, no public cloud)

## Decision Outcome

Chosen option: "One public cloud (AWS) alongside the data centres", because it meets every residency and capacity need, including GPU instances inside Nigeria through the AWS Lagos Local Zone, with one identity plane and one network path, which serves the cost, security and operations drivers best.

We will run all public-cloud workloads on AWS: EU services and data in eu-west-1, and GPU bursts for Nigerian data in the Lagos Local Zone. We will federate AWS IAM Identity Center with the bank's on-premises directory so that people have one identity.

### Consequences

* Good, because there is one identity source and one place to review access.
* Good, because one Direct Connect estate replaces two sets of private links, and no data is billed for moving between clouds.
* Good, because one Terraform codebase, one monitoring stack and one incident process cover all cloud workloads.
* Bad, because the bank depends on a single cloud provider for its EU operations and GPU capacity.
* Bad, because Azure-specific services, and any Azure skills the bank already has, go unused.

### Confirmation

* An access review shows a single federated identity source for cloud access and no standalone IAM users.
* The monthly cost report shows no inter-cloud data transfer line, and cloud spend tracks the 20% target.
* The architecture review rejects any new workload proposed for a second public cloud unless this record is superseded.

## Pros and Cons of the Options

### One public cloud (AWS) alongside the data centres

* Good, because one identity plane, one network path and one toolchain.
* Good, because AWS offers both an EU Region for EU data and in-country options in Nigeria (the Lagos Local Zone and AWS Outposts racks).
* Bad, because it concentrates dependency on one provider.

### Two public clouds (Azure for EU workloads, AWS for AI and audit)

* Good, because each workload can use the provider the team prefers for it.
* Bad, because two identity systems, two private-link estates and cross-cloud transfer charges work directly against the 20% cost cut.
* Bad, because every security control, from logging to access review, must be built and audited twice.

### Private cloud only

* Good, because every byte stays in the bank's own data centres.
* Bad, because GPU capacity for AI must be bought for the peak and sits idle between training runs.
* Bad, because EU customer data would have to be hosted in the EU by the bank itself, which needs a third data centre.

## More Information

* Related: [ADR-0002](0002-keep-nigerian-data-in-nigeria.md), and the [module write-up](../README.md).
* Confidence: high. Revisit if the bank adopts another provider for a business reason, such as an acquisition.
