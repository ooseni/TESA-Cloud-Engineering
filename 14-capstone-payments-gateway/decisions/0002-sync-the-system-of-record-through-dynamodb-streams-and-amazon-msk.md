---
status: "accepted"
date: 2026-10-18
decision-makers: Oseni Sakariyau
---

# Sync the system of record through DynamoDB Streams and Amazon MSK

> In the context of a cloud gateway whose system of record stays in a Lagos data centre, facing services that would otherwise write each state change twice, once to the cloud and once to a queue, we decided for writing each change once to DynamoDB and letting DynamoDB Streams and a relay carry it to Amazon MSK, from which a consumer in the data centre pulls, and neglected publishing from the services, Kinesis Data Streams for DynamoDB and synchronous writes over Direct Connect, to achieve every change delivered in order per payment, with payments that keep flowing when the link is down, accepting the cost of a Kafka cluster and a system of record that is seconds behind.

## Context and Problem Statement

The transaction table in the data centre stays the system of record: settlement, reconciliation, reporting and other internal systems read it, and it keeps payment records in Nigeria. The cloud tier must not need it to complete a payment, but it must receive every state change: `PENDING`, then `SUCCESS`, `FAILED` or `UNKNOWN`, then the result of any re-query. My original target design had each product service publish its state log to a Kafka topic after the vendor answered, and an asynchronous consumer copy the log into the on-premises database. A service that crashes after the vendor answers but before it publishes loses that change for good, and the record in the data centre never learns that a token was sold. How should state changes reach the system of record?

## Decision Drivers

* No state change lost, whatever fails and whenever.
* Changes to one payment arrive in the order they happened.
* Payments continue while the link to the data centre is down, for days if need be.
* The system of record's network zone accepts no connections from the cloud; it only connects out.
* A history that can be replayed for reconciliation, and room for more consumers later (notifications, fraud checks).
* Cost.

## Considered Options

* One write to DynamoDB; DynamoDB Streams and an AWS Lambda relay publish to Amazon MSK; a consumer in the data centre pulls
* Each service writes to DynamoDB and publishes to Kafka itself (my original target design)
* Kinesis Data Streams for DynamoDB, read in the data centre with the Kinesis Client Library
* Each service writes to the on-premises database synchronously over Direct Connect

## Decision Outcome

Chosen option: "One write to DynamoDB; DynamoDB Streams and an AWS Lambda relay publish to Amazon MSK; a consumer in the data centre pulls", because it removes the second write without giving up ordering, replay or a system of record that only connects out.

The services write each change to the payment's item in DynamoDB ([ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md)) and nothing else. The table's stream is the outbox: DynamoDB Streams records each change once, and in the order the changes happened to that item. A Lambda function reads the stream and publishes each change to the `transaction-state` topic on Amazon MSK, keyed by the payment's ID, so all changes to one payment land on one partition, in order. It skips the deletions made by time to live. Batches that keep failing go to an Amazon SQS dead-letter queue. The topic keeps seven days, with three replicas and `min.insync.replicas` of 2.

In the data centre, the sync consumer connects out over Direct Connect, authenticates to MSK with IAM through IAM Roles Anywhere certificates, and writes each change with an upsert that applies only a higher version than the row holds. Delivery from Lambda is at least once, so the same change can arrive twice; the version check makes that harmless. The consumer commits its offset only after the database commits.

### Consequences

* Good, because each change is written once. If the relay fails, the change is still in the stream and is retried; nothing depends on a service surviving between two writes.
* Good, because payments complete without the data centre. A link outage of up to seven days only delays the system of record, and the consumer catches up from the topic.
* Good, because the system of record's zone opens no inbound port to the cloud.
* Good, because the topic can be replayed for reconciliation, and new consumers can subscribe without touching the gateway.
* Bad, because Amazon MSK is the largest single line in the cost estimate: about $630 a month for three `kafka.m7g.large` brokers, 23% of the total.
* Bad, because it is a Kafka cluster to look after: partitions, broker size, upgrades and monitoring.
* Bad, because the system of record lags: seconds normally, longer while a backlog drains. A channel's status check reads DynamoDB, not the data centre.
* Bad, because DynamoDB Streams keeps records for 24 hours, so a relay broken for longer than that loses changes. An alarm on the relay's iterator age pages someone long before then, and the daily reconciliation compares the table with the system of record.

### Confirmation

* The demo stops the consumer, takes payments, starts it again, and checks that the system of record catches up with every payment.
* The demo replays the topic from the start and checks that the system of record does not change.
* An Amazon CloudWatch alarm on the Lambda function's `IteratorAge` above five minutes, and one on the consumer group's lag.

## Pros and Cons of the Options

### DynamoDB Streams, a Lambda relay and Amazon MSK

* Good, because the stream is derived from the table, so the record of the payment and the event about it cannot disagree.
* Good, because ordering per payment holds end to end: per item in the stream, per key in Lambda and per partition in Kafka.
* Bad, because there is a relay to run and a 24-hour window to watch.

### Each service publishes to Kafka itself

* Good, because it has the fewest parts.
* Bad, because it is two writes that can disagree: a crash, a timeout or a broker error between them loses a change, and the code to detect and repair that is the outbox pattern built by hand.

### Kinesis Data Streams for DynamoDB

* Good, because DynamoDB writes to the stream itself, so there is no relay, and Kinesis costs less than an MSK cluster at this volume.
* Bad, because AWS documents that its records "might appear in a different order than when the item changes occurred", and that duplicates can appear, so the consumer must sort by timestamp.
* Bad, because the Kinesis Client Library in the data centre needs a DynamoDB lease table and AWS API access, and ties the consumer to Kinesis.

### Synchronous writes over Direct Connect

* Good, because the system of record is never behind.
* Bad, because every payment then waits on the link and on the on-premises database, and stops when either is down.

## More Information

* Related: [ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md), [ADR-0003](0003-keep-state-revenue-payments-on-premises.md), [ADR-0005](0005-run-the-cloud-tier-in-cape-town-with-seven-day-retention.md), and the [module write-up](../README.md).
* AWS documentation: [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html), [Kinesis Data Streams for DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/kds.html), [Lambda with DynamoDB](https://docs.aws.amazon.com/lambda/latest/dg/with-ddb.html), and the [transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) in AWS Prescriptive Guidance.
* Confidence: medium. Revisit six months after go-live: if no second consumer has subscribed, Kinesis Data Streams for DynamoDB would remove the largest line in the bill, at the price of ordering in the consumer.
