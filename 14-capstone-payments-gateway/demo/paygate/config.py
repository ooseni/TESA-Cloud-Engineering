"""Settings, all from the environment. The defaults are the design's production values (see the module
README); compose.yaml shortens the timings so the tests finish in seconds."""
import os


def _seconds(name: str, default: str) -> list[float]:
    return [float(x) for x in os.environ.get(name, default).split(",")]


AWS_REGION = os.environ.get("AWS_REGION", "af-south-1")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT") or None      # unset in AWS
TABLE_NAME = os.environ.get("TABLE_NAME", "payments")

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_AUTH = os.environ.get("KAFKA_AUTH", "none")                    # none | iam (Amazon MSK)
TOPIC = os.environ.get("KAFKA_TOPIC", "transaction-state")
DLQ_TOPIC = TOPIC + ".dlq"
CONSUMER_GROUP = os.environ.get("CONSUMER_GROUP", "sor-sync")

SOR_DSN = os.environ.get("SOR_DSN", "postgresql://sor:sor@localhost:5432/sor")
VENDOR_URL = os.environ.get("VENDOR_URL", "http://localhost:8081")
VENDOR_TIMEOUT = float(os.environ.get("VENDOR_TIMEOUT", "10"))

CLAIM_WINDOW = int(os.environ.get("CLAIM_WINDOW", str(48 * 3600)))  # ADR-0001: duplicates within 48 hours
REQUERY_DELAYS = _seconds("REQUERY_DELAYS", "30,60,120,240,480")    # ADR-0004
REQUERY_WINDOW = float(os.environ.get("REQUERY_WINDOW", "900"))     # 15 minutes from the claim
STALE_PENDING = float(os.environ.get("STALE_PENDING", "60"))        # a claim with no outcome after this
WORKER_POLL = float(os.environ.get("WORKER_POLL", "5"))
