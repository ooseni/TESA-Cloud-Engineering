# Architecture decision log

One record per decision, in the MADR format. Records are immutable once accepted: a changed decision gets a new record that supersedes the old one.

| ID | Decision | Status | Date |
|---|---|---|---|
| [ADR-0001](0001-replace-the-proxy-instance-with-managed-services.md) | Replace the proxy instance with managed services, inspected by AWS Network Firewall | accepted | 2026-10-17 |
| [ADR-0002](0002-segment-the-tiers-and-chain-security-groups.md) | Segment the tiers into subnets in two zones, and chain security groups | accepted | 2026-10-17 |
| [ADR-0003](0003-contain-first-then-rebuild-tier-by-tier.md) | Contain first, then rebuild in new subnets of the same VPC, tier by tier | accepted | 2026-10-17 |
