"""The payments table (ADR-0001): one item per channel reference, claimed with a single conditional write
and changed only by writers that hold its current version."""
import hashlib
import json
import time
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from . import config

FINAL = {"SUCCESS", "FAILED"}
ATTENTION = "ATTN"          # the partition of the sparse index the re-query worker reads


def request_hash(payment: dict) -> str:
    """SHA-256 of the fields that make two requests the same payment."""
    fields = {k: payment[k] for k in ("channel", "reference", "product", "customer", "amount")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def key(channel: str, reference: str) -> str:
    return f"{channel}#{reference}"


def plain(item: dict | None) -> dict | None:
    """boto3 returns numbers as Decimal; every number here is a whole number."""
    if item is None:
        return None
    return {k: int(v) if isinstance(v, Decimal) else v for k, v in item.items()}


class Store:
    def __init__(self, table=None):
        self.table = table or boto3.resource(
            "dynamodb", region_name=config.AWS_REGION, endpoint_url=config.DYNAMODB_ENDPOINT
        ).Table(config.TABLE_NAME)

    def claim(self, payment: dict, now: float | None = None) -> tuple[bool, dict]:
        """Write the payment as PENDING if its reference is new, or its earlier claim has expired.
        Returns (True, the new item) or (False, the item that already holds the reference)."""
        now = int(now or time.time())
        item = {
            "pk": key(payment["channel"], payment["reference"]),
            "payment_id": str(uuid.uuid4()),
            **{k: payment[k] for k in ("channel", "reference", "product", "customer", "amount")},
            "request_hash": request_hash(payment),
            "status": "PENDING",
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "expires_at": now + config.CLAIM_WINDOW,
            # a claim nobody settles within STALE_PENDING is picked up by the re-query worker
            "attn_pk": ATTENTION,
            "attn_at": now + int(config.STALE_PENDING),
            "attempts": 0,
        }
        try:
            # time to live deletes expired items only "typically within a few days", so the window
            # is enforced here, not left to the deletion
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk) OR expires_at < :now",
                                ExpressionAttributeValues={":now": now},
                                ReturnValuesOnConditionCheckFailure="ALL_OLD")
            return True, item
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            existing = e.response.get("Item")
            if existing:
                existing = {k: TypeDeserializer().deserialize(v) for k, v in existing.items()}
            else:
                existing = self.get(payment["channel"], payment["reference"])
            return False, plain(existing)

    def get(self, channel: str, reference: str) -> dict | None:
        return plain(self.table.get_item(Key={"pk": key(channel, reference)}, ConsistentRead=True).get("Item"))

    def record(self, item: dict, status: str, now: float | None = None, retry_in: float | None = None,
               **fields) -> dict | None:
        """Move the item to a new status, if nobody else has changed it since `item` was read.
        retry_in keeps it on the re-query worker's list; a final status takes it off.
        Returns the new item, or None when another writer got there first."""
        now = int(now or time.time())
        names, values = {"#s": "status"}, {":s": status, ":now": now, ":one": 1, ":v": item["version"]}
        sets = ["#s = :s", "updated_at = :now", "version = version + :one"]
        for i, (k, v) in enumerate(fields.items()):
            names[f"#f{i}"], values[f":f{i}"] = k, v
            sets.append(f"#f{i} = :f{i}")
        removes = []
        if retry_in is not None:
            sets.append("attn_at = :next")
            values[":next"] = int(now + retry_in)
        elif status in FINAL or status == "REVIEW":
            removes = ["attn_pk", "attn_at"]
        expr = "SET " + ", ".join(sets) + (" REMOVE " + ", ".join(removes) if removes else "")
        try:
            return plain(self.table.update_item(
                Key={"pk": item["pk"]}, UpdateExpression=expr, ConditionExpression="version = :v",
                ExpressionAttributeNames=names, ExpressionAttributeValues=values, ReturnValues="ALL_NEW",
            )["Attributes"])
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

    def due(self, now: float | None = None, limit: int = 50) -> list[dict]:
        """Claims the re-query worker should look at now: stale PENDING ones and UNKNOWN ones whose
        next re-query is due."""
        resp = self.table.query(IndexName="attention",
                                KeyConditionExpression=Key("attn_pk").eq(ATTENTION) & Key("attn_at").lte(
                                    int(now or time.time())),
                                Limit=limit)
        return [plain(i) for i in resp["Items"]]
