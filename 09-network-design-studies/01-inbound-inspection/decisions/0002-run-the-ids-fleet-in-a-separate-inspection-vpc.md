---
status: "accepted"
date: 2026-10-17
decision-makers: Oseni Sakariyau
---

# Run the IDS fleet in a separate inspection VPC

> In the context of a third-party IDS fleet that must sit in the path of all the platform's traffic (ADR-0001), facing a security team that owns the appliances and an application team that owns the platform, we decided to run the Gateway Load Balancer and the appliances in a separate inspection VPC, shared with the application VPC only as a Gateway Load Balancer endpoint service, and neglected running the fleet inside the application VPC and a central inspection VPC behind AWS Transit Gateway, to achieve separate ownership and a fleet with no route into the platform, accepting a second VPC to run and endpoint charges in each zone.

## Context and Problem Statement

ADR-0001 puts Gateway Load Balancer endpoints in the application VPC, one per zone. The Gateway Load Balancer and its appliances must live in the same VPC as each other, but that VPC can be the application VPC or a different one. The appliances are run by the security team: their software, signatures, licences and logs. The platform is run by the application team. The medical records are in the application VPC. Where should the fleet live?

## Decision Drivers

* Separation of duties: each team can change its own side without touching the other's VPC.
* Blast radius: an appliance that is compromised should have no network path to the medical records.
* Growth: other products may need the same inspection later.
* Cost and simplicity for a single platform today.

## Considered Options

* A separate inspection VPC, shared as a Gateway Load Balancer endpoint service, with the endpoints in the application VPC
* The Gateway Load Balancer and the appliances inside the application VPC
* A central inspection VPC behind AWS Transit Gateway

## Decision Outcome

Chosen option: "A separate inspection VPC, shared as a Gateway Load Balancer endpoint service", because it keeps the two teams and their failures apart at almost no extra complexity, and leaves room to grow.

The inspection VPC (`10.51.0.0/16`) holds the Gateway Load Balancer and an Auto Scaling group of appliances in two zones. The Gateway Load Balancer is published as an endpoint service that accepts connections only from the application account, with acceptance required. The application VPC holds only the endpoints. The two VPCs are not peered and share no transit gateway: packets cross only through PrivateLink, inside GENEVE, so the appliances have no route into the application VPC. The appliances' security group admits only GENEVE (UDP 6081) and the health check from the Gateway Load Balancer's subnets. The inspection VPC has its own outbound path for signature updates and its own log pipeline (not drawn).

### Consequences

* Good, because each team owns a VPC, and its own IAM permissions, so a change on one side cannot break the other.
* Good, because a compromised appliance sees the traffic it inspects but has no route to the web, backend or records subnets.
* Good, because another product can later attach endpoints to the same service without changing the fleet.
* Bad, because there are two VPCs to run, and each zone's endpoint is charged by the hour and by the gigabyte.
* Bad, because tracing a problem means reading flow logs and metrics in both VPCs.

### Confirmation

* The endpoint service's allowed principals list only the application account, and acceptance is required.
* AWS Config, or a reviewed Terraform plan, shows no VPC peering connection or transit gateway attachment between the two VPCs.
* The appliances' security group has no inbound rule other than UDP 6081 and the health check port, both from the Gateway Load Balancer's subnets.

## Pros and Cons of the Options

### A separate inspection VPC with an endpoint service

* Good, because ownership, permissions and failures stay separate.
* Good, because more VPCs can use the same fleet later.
* Bad, because of the second VPC and the endpoint charges.

### The fleet inside the application VPC

* Good, because there are fewer moving parts: one VPC, one set of route tables.
* Bad, because both teams change the same VPC, and an appliance is one route table entry away from the medical records.
* Bad, because a second product would need a second fleet.

### A central inspection VPC behind AWS Transit Gateway

* Good, because one fleet can inspect many VPCs, including traffic between them.
* Bad, because for a single VPC it adds transit gateway attachments, data processing charges and a more complex routing design, with nothing to show for them yet.

## More Information

* Related: [ADR-0001](0001-inspect-inbound-traffic-with-a-gateway-load-balancer.md) and the [study write-up](../README.md).
* Sources: [What is a Gateway Load Balancer?](https://docs.aws.amazon.com/elasticloadbalancing/latest/gateway/introduction.html), [Create a Gateway Load Balancer endpoint service](https://docs.aws.amazon.com/vpc/latest/privatelink/create-gateway-load-balancer-endpoint-service.html), [Getting started with Gateway Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/gateway/getting-started.html) and [Centralized inspection architecture with AWS Gateway Load Balancer and AWS Transit Gateway](https://aws.amazon.com/blogs/networking-and-content-delivery/centralized-inspection-architecture-with-aws-gateway-load-balancer-and-aws-transit-gateway/).
* Confidence: high. Revisit when a second VPC needs inspection, or when traffic between VPCs must be inspected; then the Transit Gateway option becomes worth its cost.
