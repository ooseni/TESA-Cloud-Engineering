"""Calls to vendor APIs. The one rule that matters: a request that may have reached the vendor is UNKNOWN,
never FAILED, so it is re-queried and never re-sent (ADR-0004)."""
from dataclasses import dataclass

import httpx

from . import config


@dataclass
class Outcome:
    status: str                  # SUCCESS | FAILED | UNKNOWN
    token: str | None = None
    reason: str | None = None


class VendorError(Exception):
    """The vendor could not say what happened to a payment."""


def _url(item: dict) -> str:
    return f"{config.VENDOR_URL}/{item['product']}/payments"


def send(item: dict) -> Outcome:
    body = {"reference": item["payment_id"], "client_reference": item["reference"],
            "customer": item["customer"], "amount": item["amount"]}
    try:
        resp = httpx.post(_url(item), json=body, timeout=config.VENDOR_TIMEOUT)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # no connection was made, so the vendor cannot have received anything
        return Outcome("FAILED", reason="vendor unreachable; nothing was sent")
    except httpx.HTTPError as e:
        return Outcome("UNKNOWN", reason=f"no answer from the vendor: {type(e).__name__}")
    return classify(resp.status_code, resp.json() if resp.content else {})


def classify(status_code: int, body: dict) -> Outcome:
    if status_code == 200 and body.get("status") == "SUCCESS":
        return Outcome("SUCCESS", token=body.get("token"))
    if status_code in (200, 400, 402, 422) and body.get("status") == "DECLINED":
        return Outcome("FAILED", reason=body.get("reason", "declined by the vendor"))
    return Outcome("UNKNOWN", reason=f"unexpected answer from the vendor: HTTP {status_code}")


def query(item: dict) -> Outcome | None:
    """Ask the vendor what happened. None means the vendor has no record of the payment."""
    try:
        resp = httpx.get(f"{_url(item)}/{item['payment_id']}", timeout=config.VENDOR_TIMEOUT)
    except httpx.HTTPError as e:
        raise VendorError(type(e).__name__) from e
    if resp.status_code == 404:
        return None
    outcome = classify(resp.status_code, resp.json() if resp.content else {})
    if outcome.status == "UNKNOWN":
        raise VendorError(outcome.reason)
    return outcome
