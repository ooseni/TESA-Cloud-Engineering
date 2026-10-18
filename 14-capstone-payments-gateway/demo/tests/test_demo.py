"""End-to-end tests against the running demo (`docker compose up`). Each test proves one row of the
module README's failure table. They skip when the demo is not running, unless REQUIRE_DEMO=1 (as in CI)."""
import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
import httpx
import psycopg
import pytest

from paygate import consumer

DEMO = Path(__file__).resolve().parents[1]
GATEWAY, VENDOR = "http://127.0.0.1:8080", "http://127.0.0.1:8081"
SOR = "postgresql://sor:sor@127.0.0.1:15432/sor"


def _running() -> bool:
    try:
        return httpx.get(f"{GATEWAY}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _running() and os.environ.get("REQUIRE_DEMO") != "1",
                                reason="the demo is not running")


def ref() -> str:
    return uuid.uuid4().hex[:20]


def pay(customer: str, reference: str | None = None, amount: int = 150000, product: str = "electricity"):
    body = {"channel": "ussd", "reference": reference or ref(), "product": product,
            "customer": f"{customer}-{uuid.uuid4().hex[:6]}" if "-" not in customer else customer,
            "amount": amount}
    return body, httpx.post(f"{GATEWAY}/payments", json=body, timeout=15)


def wait_for(check, timeout: float = 25, every: float = 0.5):
    end = time.time() + timeout
    while time.time() < end:
        result = check()
        if result:
            return result
        time.sleep(every)
    raise AssertionError(f"not true within {timeout} s: {check.__doc__ or check}")


def deliveries(reference: str) -> int:
    return httpx.get(f"{VENDOR}/deliveries/{reference}", timeout=5).json()["count"]


def sor_row(payment_id: str) -> dict | None:
    with psycopg.connect(SOR) as conn:
        row = conn.execute("SELECT status, version, token FROM payments WHERE payment_id = %s",
                           (payment_id,)).fetchone()
    return dict(zip(("status", "version", "token"), row)) if row else None


def in_sor(payment_id: str, status: str):
    def check():
        row = sor_row(payment_id)
        return row if row and row["status"] == status else None
    check.__doc__ = f"{payment_id} is {status} in the system of record"
    return check


def compose(*args: str, stdin: str | None = None, check: bool = True) -> str:
    return subprocess.run(["docker", "compose", *args], cwd=DEMO, check=check, capture_output=True,
                          text=True, input=stdin).stdout


def kafka(tool: str, *args: str, **kwargs) -> str:
    return compose("exec", "-T", "kafka", f"/opt/kafka/bin/{tool}.sh", "--bootstrap-server", "kafka:9092",
                   *args, **kwargs)


def consumer_container(action: str) -> None:
    """Stop or start the sync consumer's container alone. `docker compose start` would also re-run the
    one-shot setup it depends on, and restart anything else in its dependency chain."""
    container = compose("ps", "-aq", "consumer").strip()
    subprocess.run(["docker", action, container], check=True, capture_output=True)


# ---------------------------------------------------------------- the payment and its duplicates

def test_a_payment_succeeds_and_reaches_the_system_of_record():
    body, r = pay("OK")
    assert r.status_code == 200 and r.json()["status"] == "SUCCESS" and r.json()["token"]
    row = wait_for(in_sor(r.json()["payment_id"], "SUCCESS"))
    assert row["version"] == 2 and row["token"] == r.json()["token"]


def test_twenty_identical_requests_at_once_are_delivered_once():
    body = {"channel": "ussd", "reference": ref(), "product": "airtime", "customer": "OK-twenty",
            "amount": 50000}
    with ThreadPoolExecutor(20) as pool:
        answers = list(pool.map(lambda _: httpx.post(f"{GATEWAY}/payments", json=body, timeout=15), range(20)))
    assert {a.json()["payment_id"] for a in answers} == {answers[0].json()["payment_id"]}
    assert {a.json()["status"] for a in answers} <= {"SUCCESS", "PENDING"}
    assert deliveries(body["reference"]) == 1
    final = httpx.get(f"{GATEWAY}/payments/ussd/{body['reference']}").json()
    assert final["status"] == "SUCCESS"
    assert {a.json()["token"] for a in answers if a.json()["status"] == "SUCCESS"} == {final["token"]}


def test_a_retry_gets_the_original_answer():
    body, first = pay("OK")
    again = httpx.post(f"{GATEWAY}/payments", json=body, timeout=15)
    assert again.status_code == 200 and again.json() == first.json()
    assert deliveries(body["reference"]) == 1


def test_a_reference_reused_for_a_different_payment_is_refused():
    body, first = pay("OK")
    changed = httpx.post(f"{GATEWAY}/payments", json={**body, "amount": body["amount"] + 1}, timeout=15)
    assert changed.status_code == 409
    assert deliveries(body["reference"]) == 1


def test_a_declined_payment_fails():
    _, r = pay("DECLINE")
    assert r.status_code == 200 and r.json()["status"] == "FAILED" and r.json()["reason"]
    wait_for(in_sor(r.json()["payment_id"], "FAILED"))


# ---------------------------------------------------------------- unknown outcomes (ADR-0004)

def test_a_late_answer_after_delivery_is_settled_by_a_requery():
    body, r = pay("SLOW")
    assert r.status_code == 202 and r.json()["status"] == "PENDING"
    wait_for(lambda: httpx.get(f"{GATEWAY}/payments/ussd/{body['reference']}").json()["status"] == "SUCCESS")
    assert deliveries(body["reference"]) == 1
    wait_for(in_sor(r.json()["payment_id"], "SUCCESS"))


def test_a_payment_lost_on_the_way_fails_when_the_window_closes():
    body, r = pay("LOST")
    assert r.status_code == 202
    wait_for(lambda: httpx.get(f"{GATEWAY}/payments/ussd/{body['reference']}").json()["status"] == "FAILED")
    assert deliveries(body["reference"]) == 0


def test_a_vendor_that_keeps_erroring_sends_the_payment_to_review():
    _, r = pay("FLAKY")
    assert r.status_code == 202
    wait_for(in_sor(r.json()["payment_id"], "REVIEW"))


def test_a_claim_left_by_a_stopped_task_is_recovered():
    """A task that stops between the claim and the vendor call leaves a PENDING claim and nothing sent."""
    reference, now = ref(), int(time.time())
    table = boto3.resource("dynamodb", region_name="af-south-1", endpoint_url="http://127.0.0.1:8000",
                           aws_access_key_id="local", aws_secret_access_key="local").Table("payments")
    payment_id = str(uuid.uuid4())
    table.put_item(Item={
        "pk": f"ussd#{reference}", "payment_id": payment_id, "channel": "ussd", "reference": reference,
        "product": "paytv", "customer": "OK-stopped", "amount": 400000, "request_hash": "x",
        "status": "PENDING", "version": 1, "created_at": now - 60, "updated_at": now - 60,
        "expires_at": now + 3600, "attn_pk": "ATTN", "attn_at": now - 1, "attempts": 0})
    wait_for(lambda: httpx.get(f"{GATEWAY}/payments/ussd/{reference}").json()["status"] == "FAILED")
    assert deliveries(reference) == 0


# ---------------------------------------------------------------- the system of record (ADR-0002)

def test_an_older_version_never_overwrites_a_newer_one():
    change = {"payment_id": str(uuid.uuid4()), "channel": "ussd", "reference": ref(), "product": "airtime",
              "customer": "OK-order", "amount": 1000, "token": "t", "reason": None, "updated_at": 2}
    with psycopg.connect(SOR) as conn:
        assert consumer.apply(conn, {**change, "status": "SUCCESS", "version": 2}) == "applied"
        assert consumer.apply(conn, {**change, "status": "PENDING", "version": 1, "updated_at": 1}) == "stale"
        assert consumer.apply(conn, {**change, "status": "SUCCESS", "version": 2}) == "stale"
    assert sor_row(change["payment_id"])["status"] == "SUCCESS"


def test_a_reference_reused_after_the_window_is_flagged_not_lost():
    first = {"payment_id": str(uuid.uuid4()), "channel": "ussd", "reference": ref(), "product": "airtime",
             "customer": "OK-reuse", "amount": 1000, "status": "SUCCESS", "version": 2, "token": "t",
             "reason": None, "updated_at": 2}
    second = {**first, "payment_id": str(uuid.uuid4())}
    with psycopg.connect(SOR) as conn:
        assert consumer.apply(conn, first) == "applied"
        assert consumer.apply(conn, second) == "flagged"
        assert conn.execute("SELECT count(*) FROM flags WHERE payment_id = %s",
                            (second["payment_id"],)).fetchone()[0] == 1


def test_a_malformed_message_goes_to_the_dead_letter_topic():
    marker = f"not-json-{uuid.uuid4().hex[:8]}"
    kafka("kafka-console-producer", "--topic", "transaction-state", stdin=marker + "\n")

    def in_dead_letters():
        return marker in kafka("kafka-console-consumer", "--topic", "transaction-state.dlq", "--from-beginning",
                               "--timeout-ms", "3000", check=False)
    wait_for(in_dead_letters, timeout=40, every=1)


def test_the_system_of_record_catches_up_after_an_outage():
    consumer_container("stop")
    try:
        paid = [pay("OK")[1].json()["payment_id"] for _ in range(5)]
        time.sleep(3)
        assert all(sor_row(p) is None for p in paid), "the consumer is stopped, so nothing should arrive"
    finally:
        consumer_container("start")
    for p in paid:
        wait_for(in_sor(p, "SUCCESS"), timeout=40)


def test_replaying_the_whole_topic_changes_nothing():
    def snapshot():
        with psycopg.connect(SOR) as conn:
            return conn.execute("SELECT payment_id, status, version, token FROM payments ORDER BY 1").fetchall()

    before = snapshot()
    consumer_container("stop")
    try:
        kafka("kafka-consumer-groups", "--group", "sor-sync", "--topic", "transaction-state", "--reset-offsets",
              "--to-earliest", "--execute")
    finally:
        consumer_container("start")

    def caught_up():
        out = kafka("kafka-consumer-groups", "--group", "sor-sync", "--describe")
        lags = [line.split()[5] for line in out.splitlines() if line.startswith("sor-sync")]
        return lags and all(lag == "0" for lag in lags)

    wait_for(caught_up, timeout=60, every=2)
    assert snapshot() == before
