---
status: "accepted"
date: 2026-10-18
decision-makers: Oseni Sakariyau
---

# Resolve unknown outcomes by re-querying, never by re-sending

> In the context of vendor calls that can time out after the vendor has already delivered, facing a gateway with no rule for a payment whose outcome it does not know, we decided for recording it as unknown, telling the channel it is pending and asking the vendor for its status until it answers or a window closes, and neglected re-sending it, failing it at once and leaving it to the end of the day, to achieve no payment delivered twice and most unknowns settled within minutes, accepting that channels must handle a pending answer.

## Context and Problem Statement

A vendor call that times out leaves the gateway not knowing whether the vendor generated the electricity token or credited the airtime. Re-sending risks delivering twice. Marking the payment failed risks refunding a customer who received what they paid for. The current-state analysis has a query scenario, in which the gateway asks a vendor for a payment's status, but no step uses it when a payment's outcome is unknown, and neither did my original target design. What should the gateway do when it does not know whether a vendor delivered?

## Decision Drivers

* Never deliver one payment twice.
* Settle most unknown outcomes automatically, within minutes.
* Give the channel an answer it can act on at every point.
* Leave a trail that operations and reconciliation can follow.

## Considered Options

* Record it as unknown, answer "pending", re-query the vendor until it answers or a window closes
* Re-send with the same vendor reference
* Mark it failed at once and reverse the customer's payment
* Leave it for the end-of-day settlement reconciliation

## Decision Outcome

Chosen option: "Record it as unknown, answer "pending", re-query the vendor until it answers or a window closes", because it is the only option that never risks a second delivery and still settles most cases quickly.

When a vendor call times out or the connection fails after the request was sent, the gateway records `UNKNOWN` and answers the channel `202 Accepted` with the status `PENDING`. A re-query worker asks the vendor for the payment's status after 30 seconds, then after 1, 2, 4 and 8 minutes, within a 15-minute window:

* the vendor reports success: the payment becomes `SUCCESS`, with the vendor's token;
* the vendor reports failure, or still has no record of the payment when the window closes: it becomes `FAILED`, and the channel reverses the customer's debit;
* the vendor keeps erroring: it becomes `REVIEW`, for operations and the settlement reconciliation.

A claim still `PENDING` after 60 seconds belongs to a task that stopped mid-payment, before or during the vendor call; the worker treats it as `UNKNOWN`. Channels learn the result by polling the status endpoint or from a callback. The gateway never sends the same payment to a vendor twice; a customer whose payment failed tries again with a new reference.

### Consequences

* Good, because no payment is ever delivered twice by the gateway.
* Good, because most unknown outcomes settle within minutes without a person.
* Bad, because every channel must handle `PENDING`: a USSD session may end before the answer, so the customer is told by SMS.
* Bad, because "no record when the window closes" counts as not delivered, which holds only if each vendor records every request it accepts. That goes into each vendor's contract, with the vendor's own status window.
* Bad, because a failure that a re-send would have fixed costs the customer a second attempt.

### Confirmation

* The demo's vendor times out after delivering: the payment ends `SUCCESS` with exactly one delivery.
* The demo's vendor never receives the request: the payment ends `FAILED` when the window closes, with no delivery.
* The demo stops a gateway task between the claim and the vendor call: the payment ends `FAILED` with no delivery.
* A CloudWatch alarm on the number of payments in `REVIEW`.

## Pros and Cons of the Options

### Re-query until it answers or a window closes

* Good, because it asks instead of guessing.
* Bad, because it needs a status query from every vendor, and a worker to run it.

### Re-send with the same vendor reference

* Good, because it settles the payment in one step when the vendor deduplicates references.
* Bad, because whether a vendor deduplicates is a property of each vendor's system; one that does not delivers twice.

### Mark it failed at once and reverse

* Good, because the channel gets a final answer immediately.
* Bad, because when the vendor did deliver, the customer keeps the token and gets the money back.

### Leave it for the end-of-day reconciliation

* Good, because it needs no new component.
* Bad, because the customer waits up to a day, and the payment stays in doubt all that time.

## More Information

* Related: [ADR-0001](0001-claim-each-payment-once-with-a-dynamodb-conditional-write.md) (the claim that makes re-sending detectable), and the [module write-up](../README.md).
* The re-query reuses the query scenario from my current-state analysis: the gateway already knows how to ask each vendor for a payment's status.
* Confidence: high. Revisit for any vendor that guarantees, in writing, that it deduplicates references; for that vendor, a re-send with the same reference is safe.
