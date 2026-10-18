"""The gateway service: claims each payment, sends it to its vendor once, records the outcome."""
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from . import config, vendors
from .store import Store, request_hash

app = FastAPI(title="Payments gateway (demo)")
store = Store()


class Payment(BaseModel):
    channel: str = Field(pattern=r"^[A-Za-z0-9-]{1,32}$")
    reference: str = Field(pattern=r"^[A-Za-z0-9-]{1,64}$")
    product: Literal["electricity", "airtime", "paytv"]   # state revenue stays in Lagos (ADR-0003)
    customer: str = Field(pattern=r"^[A-Za-z0-9-]{1,32}$")
    amount: int = Field(gt=0, le=100_000_000)              # in kobo


def answer(item: dict, response: Response) -> dict:
    """SUCCESS and FAILED are final (200). Anything else is still being settled (202, PENDING)."""
    final = item["status"] in ("SUCCESS", "FAILED")
    response.status_code = 200 if final else 202
    return {"payment_id": item["payment_id"], "status": item["status"] if final else "PENDING",
            "token": item.get("token"), "reason": item.get("reason") if final else None}


@app.post("/payments")
def create(payment: Payment, response: Response) -> dict:
    p = payment.model_dump()
    claimed, item = store.claim(p)
    if not claimed:
        if item["request_hash"] != request_hash(p):
            raise HTTPException(409, "this reference is already used for a different payment")
        return answer(item, response)          # a duplicate: the first request's outcome, whatever it is

    outcome = vendors.send(item)
    fields = {k: v for k, v in (("token", outcome.token), ("reason", outcome.reason)) if v}
    if outcome.status == "UNKNOWN":
        updated = store.record(item, "UNKNOWN", retry_in=config.REQUERY_DELAYS[0], **fields)
    else:
        updated = store.record(item, outcome.status, **fields)
    # None: the re-query worker settled the claim first; report what it decided
    return answer(updated or store.get(p["channel"], p["reference"]), response)


@app.get("/payments/{channel}/{reference}")
def status(channel: str, reference: str, response: Response) -> dict:
    item = store.get(channel, reference)
    if item is None:
        raise HTTPException(404, "no such payment")
    return answer(item, response)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
