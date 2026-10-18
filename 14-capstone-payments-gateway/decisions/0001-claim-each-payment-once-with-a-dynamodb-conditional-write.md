---
status: "accepted"
date: 2026-10-18
decision-makers: Oseni Sakariyau
---

# Claim each payment once with a DynamoDB conditional write

> In the context of a payments gateway whose channels retry and sometimes send the same payment twice at once, facing a duplicate check that today reads the database and then acts in a separate step, we decided for claiming each payment with one conditional write to Amazon DynamoDB before anything is sent to a vendor, and neglected a Redis cache, a check-then-forward cache lookup and a synchronous check against the on-premises database, to achieve no payment sent twice even when duplicates arrive together or a node fails, accepting single-digit-millisecond claims instead of sub-millisecond ones and transaction data held briefly in the cloud.

## Context and Problem Statement

Duplicate payments reach the gateway all the time: a USSD session drops and the customer dials again, an agent's terminal times out and resends, a partner bank retries a request it never saw answered, a customer taps twice. Each duplicate carries the same client reference. In the current state, every product service checks the on-premises transaction table for that reference and, in a separate step, forwards the payment to the vendor. In my original target design, the check moved to a Redis cache in the cloud, still as a read followed by a separate forward. Two identical requests that arrive together can both read "not seen" and both be sent, and an electricity token or an airtime credit sent twice is money the business cannot recover. How should the gateway make sure each payment is sent to a vendor at most once?

## Decision Drivers

* No payment sent twice, including when identical requests arrive at the same moment.
* The claim survives the loss of a node or an Availability Zone once it is acknowledged.
* A duplicate gets the original outcome back, not an error, so channels can retry safely.
* Fast enough for a 300 payments a second peak, and independent of the link to the data centre.
* Little to operate.

## Considered Options

* A conditional write to Amazon DynamoDB that claims the reference
* `SET NX` with a time to live in Amazon ElastiCache (Redis OSS or Valkey)
* Read the cache, then forward if the reference is new (my original target design)
* A synchronous check against the on-premises transaction table (close to the current state)

## Decision Outcome

Chosen option: "A conditional write to Amazon DynamoDB that claims the reference", because it is the only option that is both atomic and durable without depending on the data centre.

The gateway writes one item before it calls a vendor. Its key is the channel's ID and the channel's client reference; it holds the payment's details, a SHA-256 hash of the request, the status `PENDING`, a version number and an expiry time 48 hours ahead. The write succeeds only if no item with that key exists, or the existing one has expired:

```text
ConditionExpression: attribute_not_exists(pk) OR expires_at < :now
```

The condition enforces the 48-hour window itself, because DynamoDB's time to live deletes expired items only "typically within a few days". When the write fails, the request is a duplicate: if its hash matches, the gateway returns the stored status (and the vendor's token, once there is one); if the hash differs, it answers `409 Conflict`, because the same reference is being used for a different payment. The outcome is then written to the same item with a condition on its version, so two writers can never overwrite each other.

### Consequences

* Good, because the claim is atomic: of any number of identical requests, exactly one write succeeds.
* Good, because a write that returns success "has occurred and is durable", stored across several Availability Zones, so a claim is not lost when a node or a zone fails.
* Good, because duplicates get the original answer back, which makes every channel retry safe.
* Good, because it needs no cluster: on-demand capacity follows the load, and point-in-time recovery covers mistakes.
* Bad, because a claim takes single-digit milliseconds rather than Redis's sub-millisecond; against vendor calls that take seconds, this does not matter.
* Bad, because the item holds the customer's reference and the amount in the cloud for the window and until deletion, which [ADR-0005](0005-run-the-cloud-tier-in-cape-town-with-seven-day-retention.md) has to approve.
* Neutral, because a reference reused after 48 hours is treated as a new payment. The system of record's unique key on channel and reference catches it when the state reaches the data centre, and flags it for reconciliation.

### Confirmation

* The demo sends 20 identical requests at the same moment and checks that the vendor received exactly one, and that all 20 answers carry the same outcome.
* A request that reuses a reference with a different amount gets `409 Conflict`.
* A load test at 300 payments a second, with the 99th-percentile claim latency recorded.
* An Amazon CloudWatch alarm on a surge in failed conditional writes, the signature of a channel stuck in a retry loop.

## Pros and Cons of the Options

### A conditional write to Amazon DynamoDB

* Good, because one request both checks and claims, so there is no gap between them.
* Good, because the claim is durable once acknowledged, and the item later stores the outcome for duplicates.
* Bad, because time to live is lazy, so the window must be in the condition and expired items linger for a few days.

### `SET NX` with a time to live in Amazon ElastiCache

* Good, because `SET NX` is atomic too, and answers in well under a millisecond.
* Bad, because replication to the replica is asynchronous: AWS warns that "a small amount of data might be lost due to replication lag during failover". A claim acknowledged just before a failover can vanish, and its retry is then sent again.
* Bad, because a cluster has to be sized, patched and paid for around the clock.

### Read the cache, then forward

* Good, because it is the simplest to write.
* Bad, because the read and the forward are separate steps: two identical requests that arrive together both read "not seen" and are both sent. This is the check-then-act race the decision exists to remove.

### A synchronous check against the on-premises transaction table

* Good, because the system of record stays the only source of truth, and a unique key there is durable.
* Bad, because every payment waits on the link to Lagos and on the on-premises database, the bottleneck the migration is meant to remove.
* Bad, because when the link is down, no payment can be taken at all.

## More Information

* Related: [ADR-0002](0002-sync-the-system-of-record-through-dynamodb-streams-and-amazon-msk.md) (how the claim's changes reach the data centre), [ADR-0004](0004-resolve-unknown-outcomes-by-re-querying-never-by-re-sending.md) (what happens when the vendor does not answer), and the [module write-up](../README.md).
* AWS documentation: [condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html), [read consistency and durable writes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html), [working with expired items](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ttl-expired-items.html), [ElastiCache failover](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/AutoFailover.html).
* Amazon MemoryDB writes to a Multi-AZ transaction log before it acknowledges, which would make a Redis-style claim durable. It was not chosen because DynamoDB gives the same guarantee with no cluster to run.
* Confidence: high. Revisit if the claim's latency, not the vendor's, ever dominates the payment's response time.
