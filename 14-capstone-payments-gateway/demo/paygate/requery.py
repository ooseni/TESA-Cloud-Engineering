"""The re-query worker (ADR-0004): asks the vendor about every payment whose outcome is unknown, and about
every claim left PENDING by a task that stopped. It never sends a payment again."""
import logging
import time

from . import config, vendors
from .store import Store

log = logging.getLogger("requery")


def next_delay(attempts: int) -> float:
    delays = config.REQUERY_DELAYS
    return delays[min(attempts, len(delays) - 1)]


def settle(store: Store, item: dict, now: float | None = None) -> str:
    """Re-query one payment and record what the vendor says. Returns the status it now has."""
    now = now or time.time()
    window_closed = now >= item["created_at"] + config.REQUERY_WINDOW
    attempts = item.get("attempts", 0) + 1
    try:
        outcome = vendors.query(item)
    except vendors.VendorError as e:
        if window_closed:
            status, kwargs = "REVIEW", {"reason": f"vendor kept erroring: {e}"}
        else:
            status, kwargs = "UNKNOWN", {"retry_in": next_delay(attempts)}
    else:
        if outcome is None and window_closed:
            status, kwargs = "FAILED", {"reason": "the vendor has no record of the payment"}
        elif outcome is None:
            status, kwargs = "UNKNOWN", {"retry_in": next_delay(attempts)}
        else:
            status = outcome.status
            kwargs = {k: v for k, v in (("token", outcome.token), ("reason", outcome.reason)) if v}
    updated = store.record(item, status, now=now, attempts=attempts, **kwargs)
    return (updated or item)["status"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    store = Store()
    while True:
        for item in store.due():
            log.info("%s %s -> %s", item["pk"], item["status"], settle(store, item))
        time.sleep(config.WORKER_POLL)


if __name__ == "__main__":
    main()
