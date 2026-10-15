---
status: "accepted"
date: 2026-10-15
decision-makers: Oseni Sakariyau
---

# Keep Nigerian personal data, its backups and its logs in Nigeria

> In the context of a bank whose requirement is that Nigerian customers' personal data never leaves Nigeria, facing a recovery-time target under 15 minutes and AI workloads that need GPUs, we decided for keeping that data and every copy of it in Nigeria (two in-country data centres, the AWS Lagos Local Zone without snapshots, and in-country API endpoints) and neglected dedicated tenancy in an offshore AWS Region and offshore backups, to achieve residency by design, accepting the cost of a second data centre and fewer managed services for that data.

## Context and Problem Statement

The scenario's bank requires that Nigerian users' personal data never leaves Nigeria. AWS has no Region in Nigeria; the nearest is Africa (Cape Town) af-south-1, about 4,800 km from Lagos. My original design gave Nigerian data "dedicated" tenancy, replicated databases across Regions, and stored audit logs in Amazon S3. Tenancy only controls who shares the hardware, not where it is, so each of those choices would have moved Nigerian data abroad. Where can this data, its backups and its logs live while still meeting the recovery-time and GPU needs?

## Decision Drivers

* Residency: Nigerian personal data, backups and logs stay in Nigeria (a hard constraint).
* Recovery time under 15 minutes after the loss of a data centre.
* Core banking latency under 5 ms.
* GPU capacity for AI training on Nigerian data.
* Audit logs that cannot be altered or deleted.
* Cost.

## Considered Options

* In country only: two Nigerian data centres, the AWS Lagos Local Zone without snapshots, and in-country API endpoints
* Dedicated tenancy in AWS af-south-1, with cross-Region replication for recovery
* One data centre, with backups and logs shipped to an AWS Region

## Decision Outcome

Chosen option: "In country only", because it is the only option that keeps every copy of the data in Nigeria while still meeting the recovery-time, latency and GPU drivers.

We will keep Nigerian personal data, and every copy and log that contains it, in Nigeria. The primary data centre replicates only to a secondary data centre in Nigeria. GPU work on this data runs in the AWS Lagos Local Zone on EBS volumes tagged `data-residency=ng`, and a service control policy denies `ec2:CreateSnapshot` on volumes with that tag, because snapshots are stored in the parent Region. Audit logs that contain personal data go to a retention-locked (WORM) store in the data centre. Partner APIs that carry Nigerian data end in the Lagos data centre. Only anonymised aggregates may leave the country.

### Consequences

* Good, because residency holds by design rather than by procedure, which makes audits simpler.
* Good, because recovery stays inside Nigeria and can meet 15 minutes with automated failover between the two sites.
* Bad, because the bank pays for and runs a second data centre.
* Bad, because the Local Zone offers fewer services than a full Region, and its volumes cannot be protected by snapshots, so backups of this data must come from the data centres.
* Bad, because engineers must tag data correctly; an untagged volume escapes the snapshot guardrail.

### Confirmation

* A failover drill moves core banking to the secondary data centre and measures recovery under 15 minutes, every quarter.
* The service control policy is in place, and an AWS Config check reports no snapshots of volumes tagged `data-residency=ng`.
* A quarterly data-flow review of Direct Connect and VPC flow logs shows only aggregate datasets reaching eu-west-1.

## Pros and Cons of the Options

### In country only

* Good, because no copy of the data leaves Nigeria.
* Good, because the Lagos Local Zone gives elastic GPUs in Lagos without buying them.
* Bad, because a second data centre and in-country backups cost more than a cloud Region's managed backups.

### Dedicated tenancy in AWS af-south-1, with cross-Region replication

* Good, because managed databases, backups and failover come built in.
* Bad, because the data lives in South Africa, which breaks the residency requirement outright.
* Bad, because Cape Town is too far from Lagos for a 5 ms round trip.

### One data centre, with backups and logs shipped to an AWS Region

* Good, because it is the cheapest to run.
* Bad, because the backups and logs leave Nigeria.
* Bad, because restoring from another country is unlikely to meet a 15-minute recovery time.

## More Information

* Related: [ADR-0001](0001-use-one-public-cloud.md), and the [module write-up](../README.md).
* AWS announced the Lagos Local Zone in January 2023; AWS Outposts racks are also available in Nigeria and are an alternative way to run AWS services inside the data centres.
* Confidence: medium. Revisit if AWS opens a Region in Nigeria, or if the bank's residency requirement changes.
