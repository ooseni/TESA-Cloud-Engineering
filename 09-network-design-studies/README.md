# 09 | Network Architecture Design Studies

**Questions received:** 10 March 2026 | **Type:** four design studies, no AWS resources | **Status:** in progress, one of four done

**At a glance**

- **Outcome:** four AWS network designs, each built around one hard security requirement: inspect every inbound packet, scan only one platform's outbound traffic, call a partner's API safely, and rebuild a network after a breach.
- **Built:** for each study, traffic-flow diagrams with route tables, security group and network ACL rules, and decision records that weigh the options.
- **Stack:** Amazon VPC, Gateway Load Balancer, AWS Network Firewall, NAT gateways, Application Load Balancer, AWS WAF, Amazon EC2, Amazon RDS.
- **Proof:** every routing and filtering rule is checked against AWS documentation, and each study lists its sources.

| # | Study | The requirement it answers | Status |
|---|---|---|---|
| 1 | [Inbound inspection for a telemedicine platform](01-inbound-inspection/) | Every packet from the internet passes a third-party IDS before it reaches any component; medical records are never reachable from the internet | ✅ |
| 2 | Selective egress scanning | Outbound traffic from one platform's application servers is scanned; the other platform's bypasses the scanner | ⬜ |
| 3 | Partner API integration | A bank's application servers call a partner's API over the internet, while customer traffic and internal traffic keep strict boundaries | ⬜ |
| 4 | Flat-network remediation | A payments company's single flat subnet and overloaded proxy led to a breach; segment and rebuild it | ⬜ |

## How the studies are anonymised

The questions came from the programme's network architecture practice set. They are restated in my own words, and the company names, domains and address ranges are replaced: each study describes the business ("a telemedicine company") instead of naming one, and uses its own range from `10.50.0.0/16` upwards. No question numbers or course material are reproduced.
