"""Unit tests: no containers needed."""
import httpx
import pytest

from paygate import config, relay, requery, vendors
from paygate.store import request_hash

PAYMENT = {"channel": "ussd", "reference": "r1", "product": "airtime", "customer": "OK-1", "amount": 50000}


def test_the_request_hash_ignores_field_order_but_not_values():
    assert request_hash(PAYMENT) == request_hash(dict(reversed(list(PAYMENT.items()))))
    assert request_hash(PAYMENT) != request_hash({**PAYMENT, "amount": 50001})


@pytest.mark.parametrize("code, body, status", [
    (200, {"status": "SUCCESS", "token": "t"}, "SUCCESS"),
    (422, {"status": "DECLINED", "reason": "barred"}, "FAILED"),
    (500, {}, "UNKNOWN"),
    (200, {"status": "SOMETHING ELSE"}, "UNKNOWN"),
])
def test_vendor_answers_are_classified(code, body, status):
    assert vendors.classify(code, body).status == status


def test_a_payment_that_never_left_fails_but_one_that_may_have_arrived_is_unknown(monkeypatch):
    item = {**PAYMENT, "payment_id": "p1"}

    def refused(*a, **k):
        raise httpx.ConnectError("refused")

    def no_answer(*a, **k):
        raise httpx.ReadTimeout("late")

    monkeypatch.setattr(httpx, "post", refused)
    assert vendors.send(item).status == "FAILED"
    monkeypatch.setattr(httpx, "post", no_answer)
    assert vendors.send(item).status == "UNKNOWN"


def test_requery_delays_back_off_then_hold(monkeypatch):
    monkeypatch.setattr(config, "REQUERY_DELAYS", [30, 60, 120])
    assert [requery.next_delay(n) for n in range(5)] == [30, 60, 120, 120, 120]


class FakeStore:
    def __init__(self):
        self.calls = []

    def record(self, item, status, **kwargs):
        self.calls.append((status, kwargs))
        return {**item, "status": status}


@pytest.mark.parametrize("answer, age, expected", [
    (vendors.Outcome("SUCCESS", token="t"), 1, "SUCCESS"),
    (None, 1, "UNKNOWN"),               # no record yet, window still open: ask again later
    (None, 10_000, "FAILED"),           # no record when the window closes: it never arrived
    (vendors.VendorError("500"), 1, "UNKNOWN"),
    (vendors.VendorError("500"), 10_000, "REVIEW"),
])
def test_requery_decisions(monkeypatch, answer, age, expected):
    def query(item):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(vendors, "query", query)
    store = FakeStore()
    item = {**PAYMENT, "payment_id": "p1", "status": "UNKNOWN", "version": 2, "created_at": 1_000_000}
    assert requery.settle(store, item, now=1_000_000 + age) == expected
    if expected == "UNKNOWN":
        assert "retry_in" in store.calls[0][1]


def test_the_relay_maps_a_stream_record_and_skips_expiry():
    image = {"payment_id": {"S": "p1"}, "channel": {"S": "ussd"}, "reference": {"S": "r1"},
             "product": {"S": "airtime"}, "customer": {"S": "OK-1"}, "amount": {"N": "50000"},
             "status": {"S": "SUCCESS"}, "version": {"N": "2"}, "token": {"S": "t"}, "updated_at": {"N": "17"}}
    message = relay.to_message({"eventName": "MODIFY", "dynamodb": {"NewImage": image}})
    assert message["amount"] == 50000 and message["version"] == 2 and message["reason"] is None
    assert relay.to_message({"eventName": "REMOVE", "dynamodb": {}}) is None
