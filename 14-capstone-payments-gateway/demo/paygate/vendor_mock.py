"""A stand-in for the vendors' APIs. The customer reference picks its behaviour, so a test can ask for any
failure:

    OK...      delivers at once
    DECLINE... declines
    SLOW...    delivers, then answers too late for the gateway (the gateway sees a timeout)
    LOST...    never records the payment and answers too late (as if it was lost on the way)
    FLAKY...   answers too late, and errors on every status query

It counts deliveries per client reference, so a test can prove that nothing was delivered twice."""
import asyncio
import os
import secrets
from collections import Counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Vendor API (mock)")
LATE = float(os.environ.get("VENDOR_LATE_SECONDS", "4"))
payments: dict[str, dict] = {}       # payment ID -> what the vendor recorded
deliveries: Counter = Counter()      # client reference -> times delivered
flaky: set[str] = set()              # payment IDs whose status queries fail


class Request(BaseModel):
    reference: str            # the gateway's payment ID
    client_reference: str
    customer: str
    amount: int


@app.post("/{product}/payments")
async def pay(product: str, req: Request):
    behaviour = req.customer.split("-")[0].upper()
    if behaviour == "DECLINE":
        payments[req.reference] = {"status": "DECLINED", "reason": "customer account is barred"}
        return JSONResponse(payments[req.reference], status_code=422)
    if behaviour in ("OK", "SLOW"):
        payments[req.reference] = {"status": "SUCCESS", "token": f"{product}-{secrets.token_hex(6)}"}
        deliveries[req.client_reference] += 1
    if behaviour == "FLAKY":
        flaky.add(req.reference)
    if behaviour in ("SLOW", "LOST", "FLAKY"):
        await asyncio.sleep(LATE)
    if req.reference not in payments:
        raise HTTPException(503, "lost")
    return payments[req.reference]


@app.get("/{product}/payments/{reference}")
async def status(product: str, reference: str):
    if reference in flaky:
        raise HTTPException(500, "status service unavailable")
    if reference not in payments:
        raise HTTPException(404, "no such payment")
    return payments[reference]


@app.get("/deliveries/{client_reference}")
async def delivered(client_reference: str):
    return {"client_reference": client_reference, "count": deliveries[client_reference]}


@app.get("/health")
async def health():
    return {"status": "ok"}
