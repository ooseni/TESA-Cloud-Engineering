# Architecture decision log

One record per decision, in the MADR format. Records are immutable once accepted: a changed decision gets a new record that supersedes the old one.

The same decisions are presented to a review board in the [decision pack (PDF, 21 slides)](payments-gateway-adr-pack.pdf). It adds the requirements, the current-state and target diagrams, a payment's states and failure handling, the risk register with its heatmap, the cost estimate, the proof from the demo and the live run, the roadmap and the decision requested.

| ID | Decision | Status | Date |
|---|---|---|---|
| [ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md) | Claim each payment once with a DynamoDB conditional write | accepted | 2026-10-18 |
| [ADR-0002](0002-sync-the-system-of-record-through-dynamodb-streams-and-amazon-msk.md) | Sync the system of record through DynamoDB Streams and Amazon MSK | accepted | 2026-10-18 |
| [ADR-0003](0003-keep-state-revenue-payments-on-premises.md) | Keep state revenue payments on premises | accepted | 2026-10-18 |
| [ADR-0004](0004-resolve-unknown-outcomes-by-re-querying-never-by-re-sending.md) | Resolve unknown outcomes by re-querying, never by re-sending | accepted | 2026-10-18 |
| [ADR-0005](0005-run-the-cloud-tier-in-cape-town-with-seven-day-retention.md) | Run the cloud tier in Cape Town, holding payment data for at most seven days | proposed | 2026-10-18 |
