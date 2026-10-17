---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Call the partner's API over the internet with mutual TLS from fixed addresses

> In the context of a bank whose wallet service must call a partner's wallet-processing API over the internet and handle its responses, facing an API that moves money and a path the bank does not control, we decided to call it over HTTPS with mutual TLS, from NAT gateway Elastic IP addresses that the partner allowlists, and neglected AWS PrivateLink, a Site-to-Site VPN and an API key alone, to achieve two independent checks on every call and nothing opened inbound, accepting certificate rotation to coordinate with the partner and addresses that must never change by accident.

## Context and Problem Statement

The bank's payment portal hands wallet work to a wallet service in private subnets. Because of persistent payment problems, the bank is integrating with a partner whose backend processes wallet transactions. The wallet service must start secure API calls to the partner over the internet and handle the responses, without weakening the boundaries around customer traffic or the bank's internal traffic. The partner's backend may or may not run on AWS. How should the wallet service connect, and how do both sides know who is calling?

## Decision Drivers

* Both sides proven: the partner knows the call is from the bank, and the bank knows it is talking to the partner.
* The partner can refuse calls from anywhere else, even with stolen credentials.
* Nothing in the bank's VPC opened to inbound connections from the internet.
* Works in both Availability Zones, whatever the partner runs on.
* Responses handled safely: a timeout must never turn into a double payment.

## Considered Options

* HTTPS with mutual TLS, from NAT gateway Elastic IP addresses the partner allowlists
* AWS PrivateLink to an endpoint service the partner offers
* An AWS Site-to-Site VPN between the bank and the partner
* HTTPS with an API key only

## Decision Outcome

Chosen option: "HTTPS with mutual TLS, from allowlisted NAT gateway addresses", because it meets the requirement to use the internet while making each call prove both its network origin and its identity, and it needs nothing from the partner beyond what payment APIs usually support.

Each zone's NAT gateway has an Elastic IP address, and the partner allowlists both. The wallet service holds a client certificate, issued by the partner's certificate authority or by the bank's private one and registered with the partner. Its private key is stored in AWS Secrets Manager, encrypted with a customer managed AWS KMS key, and fetched at start-up through an interface endpoint, so it never crosses the internet. The wallet service validates the partner's certificate chain and host name, and uses TLS 1.2 or later. Every wallet request carries an idempotency key, so a request retried after a timeout cannot be applied twice; calls have timeouts, retries with backoff and a circuit breaker so that a slow partner cannot exhaust the wallet service. Outbound traffic is limited to the partner's API by a firewall ([ADR-0002](0002-allow-outbound-traffic-only-to-the-partner-api.md)).

### Consequences

* Good, because a stolen certificate is useless from another address, and a borrowed address is useless without the certificate.
* Good, because the responses arrive on connections the wallet service opened, so no inbound rule exists for the partner or anyone else.
* Good, because it works whatever the partner runs on.
* Bad, because certificates expire: renewal has to be planned with the partner, and an expired certificate stops all wallet payments.
* Bad, because the Elastic IP addresses must never be released or replaced without telling the partner first.
* Bad, because the internet path is outside AWS's network, so latency and availability between the two sides are not guaranteed.

### Confirmation

* In the partner's test environment, a call without the client certificate is refused, and a call with it from a non-allowlisted address is refused.
* An Amazon CloudWatch alarm fires 30 days before the client certificate expires.
* A synthetic canary calls the partner's health endpoint every minute from each zone.
* A test that times out and retries the same wallet request produces one transaction, not two.

## Pros and Cons of the Options

### Mutual TLS from allowlisted NAT addresses

* Good, because identity and origin are checked separately, by both sides.
* Bad, because of the certificate lifecycle and the fixed addresses to protect.

### AWS PrivateLink to the partner's endpoint service

* Good, because traffic never touches the internet, and nothing in the bank's VPC needs a route out for it.
* Bad, because it only exists if the partner runs on AWS and offers an endpoint service. If the partner does, this record should be superseded: it is the better option.

### A Site-to-Site VPN to the partner

* Good, because the whole path is an encrypted tunnel between two known ends.
* Bad, because both sides must run and monitor VPN tunnels, agree on non-overlapping address ranges, and handle tunnel maintenance, for one API.

### An API key only

* Good, because it is the simplest for both sides.
* Bad, because a leaked key works from anywhere, and the bank has no proof it is talking to the real partner beyond normal HTTPS.

## More Information

* Related: [ADR-0002](0002-allow-outbound-traffic-only-to-the-partner-api.md) and the [study write-up](../README.md).
* Sources: [NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html), [Access AWS Secrets Manager through an interface endpoint](https://docs.aws.amazon.com/secretsmanager/latest/userguide/vpc-endpoint-overview.html), [AWS PrivateLink concepts](https://docs.aws.amazon.com/vpc/latest/privatelink/concepts.html) and [What is AWS Site-to-Site VPN?](https://docs.aws.amazon.com/vpn/latest/s2svpn/VPC_VPN.html).
* Confidence: high. Revisit if the partner offers an AWS PrivateLink endpoint service.
