---
status: "accepted"
date: 2026-10-18
decision-makers: Oseni Sakariyau
---

# Keep state revenue payments on premises

> In the context of moving a payments gateway's product services to the cloud, facing state revenue integrations that are built one state at a time and reached over links that trust the data centre, we decided for leaving them, and their writes to the system of record, in the data centre and routing their payments there over Direct Connect, and neglected moving them with the other products and splitting their traffic before the gateway, to achieve a migration that does not touch any state's integration, accepting two duplicate checks and a dependence on the link for one product.

## Context and Problem Statement

Besides electricity, airtime and data, and pay-TV, the gateway collects state revenue: taxes and levies paid to state governments. In the current-state analysis, these payments go through their own integration layer, one integration per state, in front of the state systems; they check duplicates against the transaction table and record their state there like the other products. My original target design kept them on premises: the cloud gateway routes them to the integrations, which check duplicates against the on-premises database and write their state straight to it. Should state revenue move to the cloud with the other products?

## Decision Drivers

* No change to the state governments' side: every link, allowlist and certificate stays as it is.
* State revenue records reach the system of record at once, as they do today.
* One entry point for channels, whatever the product.
* Effort and risk in a migration that already moves three products.

## Considered Options

* Keep the integrations on premises; the cloud gateway routes state revenue payments to them over Direct Connect
* Move them to the cloud with the other products
* Send state revenue straight to the data centre, before the cloud gateway

## Decision Outcome

Chosen option: "Keep the integrations on premises; the cloud gateway routes state revenue payments to them over Direct Connect", because it moves the three high-volume products without renegotiating a single state's connection.

Channels keep one entry point. The gateway recognises a state revenue payment and forwards it to the state revenue service in the data centre over Direct Connect, with the Site-to-Site VPN as backup. That service checks for duplicates in the transaction table and records the payment there, as it does today, and the gateway passes its answer back. These payments do not use the DynamoDB claim or the event topic.

### Consequences

* Good, because no state integration changes, so none of the states has to approve anything.
* Good, because state revenue records are in the system of record as soon as the payment completes.
* Bad, because there are two duplicate checks: DynamoDB for three products, the transaction table for the fourth.
* Bad, because state revenue payments stop if both Direct Connect and the backup VPN fail.
* Bad, because the gateway answers status checks for them from the data centre, not from DynamoDB.

### Confirmation

* An inventory of each state integration's network dependencies (allowlisted addresses, private links, certificates) confirms which of them assume the data centre.
* A failover test: with Direct Connect down, state revenue payments complete over the backup VPN.

## Pros and Cons of the Options

### Keep the integrations on premises

* Good, because it is the least change for the most fragile, lowest-volume product.
* Bad, because it keeps a second pattern alive.

### Move them to the cloud with the other products

* Good, because one pattern covers every product.
* Bad, because each state's link and allowlist names the data centre, so every state would have to change its side, on its own timetable.

### Send state revenue straight to the data centre, before the cloud gateway

* Good, because state revenue traffic never crosses to the cloud and back.
* Bad, because channels must then know which products live where, and two entry points must be secured and monitored.

## More Information

* Related: [ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md), [ADR-0002](0002-sync-the-system-of-record-through-dynamodb-streams-and-amazon-msk.md), and the [module write-up](../README.md).
* This decision follows my original target design. The reasons are written here for the first time; the integrations' network dependencies are an assumption until the inventory confirms them.
* Confidence: medium. Revisit when states offer APIs over the internet that any address can call with credentials.
