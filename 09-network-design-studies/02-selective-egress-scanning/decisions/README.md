# Architecture decision log

One record per decision, in the MADR format. Records are immutable once accepted: a changed decision gets a new record that supersedes the old one.

| ID | Decision | Status | Date |
|---|---|---|---|
| [ADR-0001](0001-select-platform-a-traffic-by-source-subnet.md) | Select platform A's outbound traffic by source subnet | accepted | 2026-10-17 |
| [ADR-0002](0002-scan-with-aws-network-firewall.md) | Scan platform A's outbound traffic with AWS Network Firewall | accepted | 2026-10-17 |
| [ADR-0003](0003-put-the-firewall-before-the-nat-gateway.md) | Put the firewall before the NAT gateway, with a route back through it | accepted | 2026-10-17 |
