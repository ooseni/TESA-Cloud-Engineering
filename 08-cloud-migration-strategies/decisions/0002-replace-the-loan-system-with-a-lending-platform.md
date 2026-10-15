---
status: "accepted"
date: 2026-10-15
decision-makers: Oseni Sakariyau
---

# Replace the loan system with a commercial lending platform

> In the context of an in-house loan system that is slow and cannot scale, facing fintech competitors that approve loans faster and a rule that keeps loan records on premises, we decided for buying a commercial lending platform that runs in the bank's data centre and neglected rebuilding it in the cloud, moving it unchanged and buying a lending service hosted abroad, to achieve automated loan decisions within six months without a new system to maintain, accepting licence costs, less room to differentiate and a platform that still sits on premises.

## Context and Problem Statement

The bank built its loan processing system in house. Staff use it for loan approvals and credit checks, and it is slow and does not scale, while competing fintechs approve loans digitally in minutes. Loan applications and records are sensitive financial data, so under the scenario's rule they stay in the bank's data centre. The same small IT team is refactoring the mobile banking backend in the same six months ([ADR-0001](0001-refactor-mobile-banking-into-the-lagos-local-zone.md)), and the bank's internal systems are already expensive and hard to maintain. Which migration strategy gets the bank fast loan decisions soonest?

## Decision Drivers

* Faster loan decisions, with automated credit checks.
* Time to market: live within six months.
* Loan records stay at rest in the bank's data centre.
* Less in-house software to maintain.
* Team capacity, already committed to the mobile refactor.
* Integration with core banking and the credit bureaus.

## Considered Options

* Repurchase: a commercial lending platform that runs in the bank's data centre
* Refactor: rebuild the system in house as cloud-native services, with loan records in the data centre
* Replatform: move the current system to containers and a managed database
* Repurchase a lending platform as a service hosted outside Nigeria

## Decision Outcome

Chosen option: "Repurchase: a commercial lending platform that runs in the bank's data centre", because it delivers automated decisions fastest, keeps loan records on premises, and stops the bank maintaining its own loan software.

We will buy a loan origination and decisioning platform that the vendor supports and upgrades, install it in the bank's data centre, and connect it to core banking's API and to the credit bureaus. The tender requires deployment in the bank's data centre, credit rules the bank can configure without code, an API for the mobile app, vendor-supported upgrades, and a contract clause to export all loan data in an open format. Open loans move to the new platform and are reconciled against core banking; the in-house system is then switched off.

### Consequences

* Good, because a proven platform brings automated credit checks and decisions in months, not a multi-year build.
* Good, because the vendor carries upgrades and fixes, which shrinks the in-house estate the bank struggles to maintain.
* Good, because loan records stay in the bank's data centre.
* Good, because the team's refactoring effort stays focused on the mobile backend.
* Bad, because licence fees replace development costs, and the bank depends on the vendor's roadmap.
* Bad, because a product offers less room to differentiate than a system built for the bank's own lending model.
* Bad, because the platform runs on premises, so it does not shrink the data centre.
* Bad, because moving open loans needs careful reconciliation.

### Confirmation

* In a pilot branch, the time from a complete application to a decision is measured before and after the switch, against a target the business sets.
* After migration, every open loan's balance matches core banking exactly.
* The data-export clause is tested during acceptance: a full export is produced and checked.

## Pros and Cons of the Options

### Repurchase: a commercial lending platform in the bank's data centre

* Good, because it is the fastest route to automated decisions.
* Good, because maintenance moves to the vendor.
* Bad, because of licence costs and vendor lock-in.

### Refactor: rebuild in house as cloud-native services

* Good, because the bank controls every feature, including its own credit scoring.
* Bad, because it is the slowest option and needs credit-decisioning expertise the team does not have.
* Bad, because it competes with the mobile refactor for the same people.
* Bad, because it recreates the in-house maintenance burden the bank wants to escape.

### Replatform: move the current system to containers and a managed database

* Good, because it changes little and could run on newer infrastructure.
* Bad, because the system is slow by design and by process; moving it does not make decisions faster.
* Bad, because loan records must stay on premises, which rules out a managed database in an AWS Region.

### Repurchase a lending platform hosted outside Nigeria

* Good, because it is the quickest to start and needs no infrastructure.
* Bad, because loan records would be stored outside the bank's data centre, which breaks the scenario's rule.

## More Information

* Related: [ADR-0001](0001-refactor-mobile-banking-into-the-lagos-local-zone.md), [ADR-0003](0003-move-kyc-documents-to-amazon-s3-in-cape-town.md), and the [module write-up](../README.md).
* AWS Prescriptive Guidance lists replacing a custom application with a vendor product as a use case for the repurchase strategy.
* Confidence: medium. Revisit when the regulator allows financial data in the cloud: the vendor's hosted edition would then remove the on-premises footprint too.
