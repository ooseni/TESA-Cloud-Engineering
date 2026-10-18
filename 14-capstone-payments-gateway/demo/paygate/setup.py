"""Creates the demo's payments table, topics and system-of-record schema. Safe to run again.
On AWS, Terraform has already created the table, so only the topics and the schema are made here."""
import time
from pathlib import Path

import boto3
import psycopg
from botocore.exceptions import ClientError
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

from . import config
from .kafka_client import admin


def retry(what: str, fn, attempts: int = 60):
    for n in range(attempts):
        try:
            return fn()
        except Exception as e:          # the dependency is still starting
            if n == attempts - 1:
                raise
            print(f"waiting for {what}: {type(e).__name__}", flush=True)
            time.sleep(2)


def table() -> None:
    ddb = boto3.client("dynamodb", **config.aws_kwargs())
    try:
        ddb.describe_table(TableName=config.TABLE_NAME)
        return                                  # Terraform made it (AWS), or an earlier run did
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    try:
        ddb.create_table(
            TableName=config.TABLE_NAME, BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": n, "AttributeType": t}
                                  for n, t in (("pk", "S"), ("attn_pk", "S"), ("attn_at", "N"))],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[{
                "IndexName": "attention",
                "KeySchema": [{"AttributeName": "attn_pk", "KeyType": "HASH"},
                              {"AttributeName": "attn_at", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            }],
            StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_IMAGE"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceInUseException":
            raise
    ddb.get_waiter("table_exists").wait(TableName=config.TABLE_NAME)
    if ddb.describe_time_to_live(TableName=config.TABLE_NAME)["TimeToLiveDescription"].get(
            "TimeToLiveStatus") not in ("ENABLED", "ENABLING"):
        ddb.update_time_to_live(TableName=config.TABLE_NAME,
                                TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"})


def topics() -> None:
    client = admin()
    for name, partitions in ((config.TOPIC, 12), (config.DLQ_TOPIC, 1)):
        try:
            client.create_topics([NewTopic(name, num_partitions=partitions,
                                           replication_factor=config.TOPIC_REPLICATION)])
        except TopicAlreadyExistsError:
            pass


def schema() -> None:
    with psycopg.connect(config.SOR_DSN) as conn:
        conn.execute((Path(__file__).parent / "schema.sql").read_text())


def main() -> None:
    retry("DynamoDB", table)
    retry("Kafka", topics)
    retry("the system of record", schema)
    print("setup complete", flush=True)


if __name__ == "__main__":
    main()
