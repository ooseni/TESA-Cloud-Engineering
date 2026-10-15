---
status: "proposed"
date: 2026-10-15
decision-makers: Oseni Sakariyau
---

# Move KYC documents to Amazon S3 in Cape Town

> In the context of a document system whose customer KYC documents need large, secure, scalable storage that every branch can reach, facing ageing hardware and no AWS Region in Nigeria, we propose replatforming the documents to Amazon S3 in Africa (Cape Town) af-south-1 and neglected keys held in the bank's own HSM, S3 on Outposts and keeping the documents on new on-premises hardware, to achieve durable storage that grows without hardware, accepting that the documents leave Nigeria, which needs the compliance team's approval first.

## Context and Problem Statement

The bank's document management system stores customer KYC documents: identity documents, photographs and proof of address. The store is large and growing, must be secure and scalable, and is read often by staff in many branches. The scenario's rule keeps sensitive financial data on premises; KYC documents are personal data that identify customers rather than financial records, and whether the rule covers them is for the bank's compliance team to decide. That is why this record is proposed, not accepted. AWS has no Region in Nigeria, the Lagos Local Zone does not offer Amazon S3, and S3 on Outposts needs a first-generation Outposts rack, whose smallest one-year configuration is 960 vCPUs and 20 TB of EBS storage. Where should the documents live?

## Decision Drivers

* Durable, encrypted storage that grows without buying hardware.
* Fast enough for branch staff opening documents all day.
* Lower data-centre costs and no more ageing storage hardware.
* Whether KYC documents may be stored outside Nigeria: the compliance team decides, under the scenario's rule and the Nigeria Data Protection Act 2023's conditions for transfers abroad.
* Documents kept for the retention period the bank's records policy sets.

## Considered Options

* Replatform to Amazon S3 in af-south-1, reached over AWS Direct Connect
* The same, with the keys held in the bank's own HSM through an AWS KMS external key store
* S3 on Outposts in the bank's data centre
* Retain: keep the documents on the bank's own storage, on new hardware

## Decision Outcome

Proposed option: "Replatform to Amazon S3 in af-south-1, reached over AWS Direct Connect", because it meets the storage, cost and branch-access drivers at the lowest cost, provided the compliance team agrees that KYC documents may be stored in South Africa.

If it is approved, we will move the documents to an S3 bucket in af-south-1 encrypted with a customer managed AWS KMS key, with S3 Block Public Access on, versioning on so an overwritten or deleted document can be recovered, and a bucket policy that admits requests only through the VPC's S3 gateway endpoint. S3 Intelligent-Tiering moves documents nobody opens to cheaper tiers, and a lifecycle rule expires old versions once the retention period ends. The document application moves to Amazon EC2 in the same Region and reads and writes S3 instead of local file servers. AWS DataSync copies the existing documents over Direct Connect and verifies every file, then branches switch over one at a time. If compliance does not approve, this record is superseded by one that retains the documents on premises.

### Consequences

* Good, because Amazon S3 is designed for 99.999999999% durability and stores data across at least three Availability Zones.
* Good, because capacity grows without hardware, and documents nobody opens move to cheaper tiers on their own.
* Good, because access is private: through Direct Connect and a gateway endpoint, with no public access.
* Bad, because the documents are stored outside Nigeria, which needs the compliance team's approval and the transfer conditions of the Nigeria Data Protection Act 2023.
* Bad, because every request from a branch crosses at least 48 ms to Cape Town and back: fine for opening a document, noticeable for bulk work.
* Bad, because branch access depends on Direct Connect, so the connection needs a backup.

### Confirmation

* The compliance team's approval is recorded before the first document is copied.
* DataSync's verification reports no mismatched files, and document counts match between the old store and the bucket.
* AWS Config reports S3 Block Public Access on and the bucket encrypted with the customer managed key.
* In a pilot branch, staff open documents within a time target the bank sets.

## Pros and Cons of the Options

### Replatform to Amazon S3 in af-south-1

* Good, because it is durable, encrypted and grows on demand.
* Good, because it retires the ageing storage hardware.
* Bad, because the documents leave Nigeria.

### The same, with the keys in the bank's own HSM (AWS KMS external key store)

* Good, because AWS cannot decrypt the documents without the bank's key manager, and the bank can cut access at any time.
* Bad, because AWS recommends a round trip of 35 ms or less to the external key manager, and Lagos to Cape Town is at least 48 ms.
* Bad, because AWS warns that for most workloads the extra availability and latency risk outweighs the benefit: if the bank's key manager is unreachable, no document can be opened.
* Bad, because the documents are still stored in South Africa, so it does not remove the need for approval.

### S3 on Outposts in the bank's data centre

* Good, because the documents stay on premises with the S3 API.
* Bad, because the smallest one-year rack configuration, 960 vCPUs and 20 TB of EBS storage, is far beyond a microfinance bank's needs.
* Bad, because the rack lives in the data centre the bank wants to shrink.

### Retain on new on-premises hardware

* Good, because the documents never leave the data centre and no approval is needed.
* Bad, because the bank buys, runs and eventually replaces storage again, the opposite of what it wants.

## More Information

* Related: [ADR-0001](0001-refactor-mobile-banking-into-the-lagos-local-zone.md), [ADR-0002](0002-replace-the-loan-system-with-a-lending-platform.md), and the [module write-up](../README.md).
* Sources: [Amazon S3 data durability](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DataDurability.html), [AWS KMS external key stores](https://docs.aws.amazon.com/kms/latest/developerguide/keystore-external.html), [AWS Outposts rack FAQs](https://aws.amazon.com/outposts/rack/faqs/), [AWS DataSync](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html) and [gateway endpoints for Amazon S3](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html).
* Confidence: medium, pending the compliance decision. Revisit if AWS opens a Region in Nigeria.
