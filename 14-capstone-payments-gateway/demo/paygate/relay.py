"""The relay (ADR-0002): publishes each change to a payment, read from the table's stream, to the
transaction-state topic, keyed by payment ID so that one payment's changes stay in order.

`handler` is the AWS Lambda function. `main` stands in for Lambda's event source mapping on a laptop: it
reads DynamoDB Local's stream and hands the records to `handler` in the same event shape."""
import json
import logging
import time

import boto3
from boto3.dynamodb.types import TypeDeserializer

from . import config
from .kafka_client import producer

log = logging.getLogger("relay")
FIELDS = ("payment_id", "channel", "reference", "product", "customer", "amount", "status", "version",
          "token", "reason", "updated_at")
_producer = None


def to_message(record: dict) -> dict | None:
    """The topic message for one stream record, or None for a record to skip. The gateway never deletes
    items, so a REMOVE is time to live clearing an expired claim; the system of record keeps the payment."""
    if record["eventName"] == "REMOVE":
        return None
    image = {k: TypeDeserializer().deserialize(v) for k, v in record["dynamodb"]["NewImage"].items()}
    return {k: int(image[k]) if k in ("amount", "version", "updated_at") else image.get(k) for k in FIELDS}


def handler(event: dict, context=None) -> dict:
    """Publish a batch and wait for every acknowledgement. Any failure raises, so Lambda retries the batch:
    duplicates are harmless downstream, losses are not."""
    global _producer
    _producer = _producer or producer()
    sent = [_producer.send(config.TOPIC, key=m["payment_id"].encode(), value=json.dumps(m).encode())
            for m in map(to_message, event["Records"]) if m]
    for future in sent:
        future.get(timeout=30)
    return {"published": len(sent)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    streams = boto3.client("dynamodbstreams", **config.aws_kwargs())
    table = boto3.client("dynamodb", **config.aws_kwargs()).describe_table(TableName=config.TABLE_NAME)
    arn = table["Table"]["LatestStreamArn"]
    iterators: dict[str, str | None] = {}          # shard ID -> next iterator; None once a shard is closed
    while True:
        for shard in streams.describe_stream(StreamArn=arn)["StreamDescription"]["Shards"]:
            sid = shard["ShardId"]
            if sid not in iterators:
                iterators[sid] = streams.get_shard_iterator(StreamArn=arn, ShardId=sid,
                                                            ShardIteratorType="TRIM_HORIZON")["ShardIterator"]
        for sid, it in list(iterators.items()):
            if it is None:
                continue
            resp = streams.get_records(ShardIterator=it, Limit=100)
            iterators[sid] = resp.get("NextShardIterator")
            if resp["Records"]:
                log.info("%s", handler({"Records": resp["Records"]}))
        time.sleep(0.2)


if __name__ == "__main__":
    main()
