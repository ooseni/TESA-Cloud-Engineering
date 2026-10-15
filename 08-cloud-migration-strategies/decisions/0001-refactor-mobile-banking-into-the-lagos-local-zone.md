---
status: "accepted"
date: 2026-10-15
decision-makers: Oseni Sakariyau
---

# Refactor the mobile banking backend into the Lagos Local Zone

> In the context of a mobile banking backend that goes down at salary-day and festive peaks, facing a core banking system that must stay in the bank's data centre, we decided for refactoring it into stateless services in the AWS Lagos Local Zone, moved one route at a time, and neglected rehosting it in Cape Town, replatforming it unchanged and buying more servers, to achieve capacity that follows demand and a short path to core banking, accepting the cost of a refactor and a single-zone location.

## Context and Problem Statement

The bank's mobile app (transfers, bill payments, airtime) runs on a backend that already exposes APIs but is tied to the legacy systems behind it. At salary periods and festive seasons it slows down and fails, and customers complain. Core banking is retained in the bank's data centre in Lagos because sensitive financial data must stay on premises, so every balance and transfer still goes there. AWS has no Region in Nigeria: the nearest, Africa (Cape Town) af-south-1, is at least 48 ms away and back. The Lagos Local Zone offers Amazon EC2 (T3, C5, R5, G4dn and M5), Amazon EBS gp2, Application Load Balancers, Amazon ECS, Amazon EKS and AWS Direct Connect, but not AWS Fargate, Amazon RDS, Amazon ElastiCache, Amazon S3 or NAT gateways. Which migration strategy fixes the outages, and where should the backend run?

## Decision Drivers

* Stay up through salary-day and festive peaks.
* Launch new digital products quickly.
* Sensitive financial data stays at rest in the bank's data centre.
* A short round trip to core banking, which stays in Lagos.
* Delivered within six months, with a way back at every step.

## Considered Options

* Refactor into stateless services in the Lagos Local Zone, one route at a time
* Rehost the current backend on Amazon EC2 in af-south-1
* Replatform: containerise the current backend unchanged in the Lagos Local Zone
* Keep it on premises and buy servers for the peak

## Decision Outcome

Chosen option: "Refactor into stateless services in the Lagos Local Zone, one route at a time", because it is the only option that removes the cause of the outages while keeping customer data in Nigeria and close to core banking.

We will rebuild the backend as stateless services on Amazon ECS with Amazon EC2 capacity, behind an Application Load Balancer in the Lagos Local Zone, and connect them to the data centre over AWS Direct Connect. Routes move one at a time, following the strangler fig pattern: the load balancer sends each migrated route to the new services, and the old backend serves the rest until every route has moved. The services store no financial records. Balances and transfers are read and written in core banking, synchronously. Bill payments and airtime top-ups go through a message queue in the bank's data centre, so a salary-day surge waits in line instead of overloading core banking; the app shows them as processing and notifies the customer when they complete. Scheduled scaling adds capacity before salary days and festive seasons, and target tracking handles the rest. The old backend stays ready as the fallback until the new services have carried a full salary cycle.

### Consequences

* Good, because capacity follows demand and is paid for by the hour, instead of being bought for the peak.
* Good, because calls to core banking stay in Lagos over Direct Connect, a few milliseconds instead of at least 48 ms to Cape Town, and customer data in transit stays in Nigeria.
* Good, because each route can move back to the old backend, so the six-month plan never depends on a single cutover.
* Good, because new products are added as new services, without touching the old backend.
* Bad, because refactoring is the most complex and costly migration strategy; the team needs container and CI/CD skills, from training or a partner.
* Bad, because the Lagos Local Zone is one location, not a Region with several Availability Zones.
* Bad, because the Local Zone has fewer managed services: no Fargate, no ElastiCache and no NAT gateway, so the team runs the EC2 capacity for ECS.
* Bad, because core banking still limits synchronous transfers; the queue protects it only for operations that can wait.

### Confirmation

* Before the first salary day on the new services, a load test at the last salary-day peak plus a margin the bank sets, with error rate and 95th-percentile latency measured against a service level objective.
* Through the first salary period after cutover: no outage, with Amazon CloudWatch alarms on the load balancer's 5xx rate and target response time.
* A review confirms that no service writes customer data to disk in the Local Zone: EBS volumes hold only the operating system and container images.

## Pros and Cons of the Options

### Refactor into stateless services in the Lagos Local Zone

* Good, because it fixes the coupling that causes the outages, not just the server count.
* Good, because it keeps the round trip to core banking short.
* Bad, because it takes the most effort and the newest skills.

### Rehost the current backend on Amazon EC2 in af-south-1

* Good, because it is the quickest move and the full set of Regional services is available.
* Bad, because the same design moves to the cloud, so peaks still overwhelm it.
* Bad, because every call to core banking crosses at least 48 ms there and back, several times per request.
* Bad, because customer data in transit leaves Nigeria.

### Replatform: containerise the current backend unchanged in the Lagos Local Zone

* Good, because it is less work than a refactor and the API tier can scale.
* Bad, because the tight coupling to the legacy backend stays, so at the peak the bottleneck moves to core banking.
* Bad, because it does nothing to speed up new products.

### Keep it on premises and buy servers for the peak

* Good, because it needs no new skills and no data leaves the data centre.
* Bad, because capacity bought for salary days and festive seasons sits idle the rest of the time.
* Bad, because it adds hardware to a data centre the bank is trying to shrink.

## More Information

* Related: [ADR-0002](0002-replace-the-loan-system-with-a-lending-platform.md), [ADR-0003](0003-move-kyc-documents-to-amazon-s3-in-cape-town.md), and the [module write-up](../README.md).
* AWS Prescriptive Guidance describes refactoring as the most complex migration strategy and the [strangler fig pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/strangler-fig.html) as a way to replace a system gradually.
* Services in the Lagos Local Zone: [AWS Local Zones features](https://aws.amazon.com/about-aws/global-infrastructure/localzones/features/).
* Confidence: medium. Revisit if AWS opens a Region in Nigeria, if the regulator allows financial data in the cloud, or if the Local Zone cannot meet the availability target.
