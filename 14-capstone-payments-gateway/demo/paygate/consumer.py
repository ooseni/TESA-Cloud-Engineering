"""The sync consumer (ADR-0002), in the Lagos data centre: pulls the transaction-state topic and writes each
change to the system of record, applying only versions newer than the row holds. Delivery is at least once,
so the same change can arrive twice; the version check makes that harmless."""
import json
import logging
import signal

import psycopg
from psycopg import errors

from . import config
from .kafka_client import consumer, producer

log = logging.getLogger("consumer")

UPSERT = """
INSERT INTO payments (payment_id, channel, reference, product, customer, amount, status, version,
                      token, reason, updated_at)
VALUES (%(payment_id)s, %(channel)s, %(reference)s, %(product)s, %(customer)s, %(amount)s, %(status)s,
        %(version)s, %(token)s, %(reason)s, to_timestamp(%(updated_at)s))
ON CONFLICT (payment_id) DO UPDATE
   SET status = EXCLUDED.status, version = EXCLUDED.version, token = EXCLUDED.token,
       reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at
 WHERE payments.version < EXCLUDED.version
"""
FLAG = """
INSERT INTO flags (payment_id, channel, reference, reason)
VALUES (%(payment_id)s, %(channel)s, %(reference)s, 'reference already recorded for another payment')
ON CONFLICT (payment_id) DO NOTHING
"""


def apply(conn: psycopg.Connection, change: dict) -> str:
    """Write one change and commit. Returns applied, stale (an older or repeated version) or flagged
    (a reference reused after the 48-hour window: kept aside for reconciliation)."""
    try:
        with conn.cursor() as cur:
            cur.execute(UPSERT, change)
            result = "applied" if cur.rowcount == 1 else "stale"
        conn.commit()
        return result
    except errors.UniqueViolation:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(FLAG, change)
        conn.commit()
        return "flagged"


def parse(raw: bytes) -> dict:
    change = json.loads(raw)
    missing = {"payment_id", "channel", "reference", "status", "version", "updated_at"} - change.keys()
    if missing:
        raise ValueError(f"missing {sorted(missing)}")
    return change


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    source, dlq = consumer(config.TOPIC), producer()
    stopping = []
    # ECS and Docker stop a task with SIGTERM. Leaving the group then hands the partitions to a replacement
    # at once; a consumer that is simply killed holds them until its session times out (45 s).
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    with psycopg.connect(config.SOR_DSN) as conn:
        while not stopping:
            batches = source.poll(timeout_ms=1000)
            for records in batches.values():
                for record in records:
                    try:
                        change = parse(record.value)
                    except ValueError as e:     # json.JSONDecodeError is a ValueError too
                        log.warning("to the dead-letter topic: %s", e)
                        dlq.send(config.DLQ_TOPIC, value=record.value).get(timeout=30)
                        continue
                    log.info("%s v%s %s: %s", change["payment_id"], change["version"], change["status"],
                             apply(conn, change))
            if batches:
                source.commit()                 # only after the database has committed every change
    source.close(autocommit=False)
    dlq.close()
    log.info("stopped")


if __name__ == "__main__":
    main()
