---
status: "proposed"
date: 2026-10-18
decision-makers: Oseni Sakariyau
consulted: compliance (pending)
---

# Run the cloud tier in Cape Town, holding payment data for at most seven days

> In the context of a Nigerian payments gateway moving three products to AWS, facing no AWS Region in Nigeria and a Lagos Local Zone without DynamoDB, Amazon MSK or AWS Fargate, we propose running the cloud tier in Africa (Cape Town) af-south-1, holding payment data there for at most seven days with the system of record kept in Lagos, and neglect the Lagos Local Zone with self-managed stores, a European Region and staying on premises, to achieve managed, multi-zone services on the closest Region, accepting at least 48 ms each way to Lagos and a dependency on compliance's approval.

## Context and Problem Statement

AWS has no Region in Nigeria. The Lagos Local Zone offers Amazon EC2, Amazon EBS, Application Load Balancers, Amazon ECS, Amazon EKS and AWS Direct Connect, but not AWS Fargate, Amazon RDS, Amazon ElastiCache, Amazon S3 or NAT gateways ([module 08](../../08-cloud-migration-strategies/README.md)); DynamoDB, Amazon MSK and AWS Lambda run in Regions only. The nearest Region, Africa (Cape Town) af-south-1, is at least 48 ms from Lagos and back. The cloud tier holds, for each payment, the customer's reference (a meter, phone or smartcard number), the amount and the vendor's answer. Payment data in Nigeria is regulated, and whether it may be processed and held briefly outside the country is for the processor's compliance team to decide, not for this design. Where should the cloud tier run?

## Decision Drivers

* Payment data handled the way the regulator allows, with the long-term record in Nigeria.
* Managed services across several Availability Zones: DynamoDB, Amazon MSK, AWS Lambda, AWS Fargate.
* The shortest round trip to channels and vendors, which are in Nigeria.
* A design the team can run without operating its own databases and Kafka.

## Considered Options

* Africa (Cape Town) af-south-1, keeping payment data for at most seven days
* The Lagos Local Zone, with Kafka and the claim store self-managed on Amazon EC2
* A European Region, such as Europe (London) eu-west-2
* Stay on premises and scale the current gateway

## Decision Outcome

Proposed option: "Africa (Cape Town) af-south-1, keeping payment data for at most seven days", because it is the closest Region with every managed service the design needs across three Availability Zones, and it keeps the record of every payment in Lagos.

Data in the cloud is kept to what the gateway needs while a payment is in flight: claims expire after 48 hours ([ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md)) and events after seven days ([ADR-0002](0002-sync-the-system-of-record-through-dynamodb-streams-and-amazon-msk.md)). Everything is encrypted with customer managed AWS KMS keys in af-south-1. The system of record, reports and settlement stay in the data centre in Lagos, and Direct Connect from the Lagos location carries traffic to and from Cape Town. A service control policy keeps every resource in af-south-1. The status stays proposed until compliance approves it in writing.

### Consequences

* Good, because every service in the design is managed and spread across three Availability Zones.
* Good, because no payment record lives in the cloud for more than seven days.
* Bad, because every payment crosses the distance twice: channel to Cape Town, then Cape Town to the vendor in Nigeria. At least 96 ms of each payment's time is the speed of light.
* Bad, because af-south-1 is an opt-in Region, and its prices are higher than Europe's.
* Bad, because the design depends on an approval it cannot grant itself. If compliance refuses, the Local Zone option is the fallback, at the cost of running Kafka and the claim store on EC2 in a single location.

### Confirmation

* Compliance's written approval of the data held, where, and for how long, before any production traffic.
* A latency test from Lagos to the load balancer and from the gateway to each vendor over its VPN.
* The service control policy, and an AWS Config rule that reports any resource outside af-south-1.

## Pros and Cons of the Options

### Africa (Cape Town) af-south-1

* Good, because it has the managed services and three Availability Zones, and it is the nearest Region.
* Bad, because payment data leaves Nigeria for up to seven days.

### The Lagos Local Zone, self-managed stores

* Good, because payment data stays in Nigeria, a few milliseconds from channels and vendors.
* Bad, because it is a single location, not three Availability Zones.
* Bad, because Kafka and the claim store run on EC2: the team patches, backs up and fails them over itself, the work this migration was meant to hand to AWS.

### A European Region

* Good, because Europe (London) is the home Region of the Lagos Direct Connect location, and prices are lower.
* Bad, because it is no closer: Lagos is about 5,000 km from London and 4,800 km from Cape Town. And data leaves Africa as well as Nigeria.

### Stay on premises

* Good, because no data leaves the data centre and nothing new has to be approved.
* Bad, because the capacity and the single transaction table that limit the gateway today stay as they are.

## More Information

* Related: [ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md), [ADR-0002](0002-sync-the-system-of-record-through-dynamodb-streams-and-amazon-msk.md), and the [module write-up](../README.md). [Module 08's ADR-0003](../../08-cloud-migration-strategies/decisions/0003-move-kyc-documents-to-amazon-s3-in-cape-town.md) waits on the same kind of approval.
* AWS: [AWS Local Zones features](https://aws.amazon.com/about-aws/global-infrastructure/localzones/features/), [Direct Connect in Lagos](https://aws.amazon.com/about-aws/whats-new/2023/05/aws-direct-connect-location-lagos-nigeria/).
* Confidence: medium. Revisit if AWS opens a Region in Nigeria, or adds these services to the Lagos Local Zone.
