"""Kafka clients. Locally the broker takes plain connections; on Amazon MSK they use TLS and IAM
authentication, with short-lived tokens signed from the caller's AWS credentials (no stored secret)."""
from kafka import KafkaConsumer, KafkaProducer

from . import config


def _auth() -> dict:
    if config.KAFKA_AUTH != "iam":
        return {}
    from aws_msk_iam_sasl_signer import MSKAuthTokenProvider
    from kafka.sasl.oauth import AbstractTokenProvider

    class MSKToken(AbstractTokenProvider):
        def token(self):
            return MSKAuthTokenProvider.generate_auth_token(config.AWS_REGION)[0]

    return {"security_protocol": "SASL_SSL", "sasl_mechanism": "OAUTHBEARER",
            "sasl_oauth_token_provider": MSKToken()}


def producer() -> KafkaProducer:
    # acks=all: a message counts as sent only when every in-sync replica has it.
    # One request in flight per connection keeps a payment's changes in order through retries.
    return KafkaProducer(bootstrap_servers=config.KAFKA_BOOTSTRAP, acks="all", retries=5,
                         max_in_flight_requests_per_connection=1, **_auth())


def consumer(*topics: str) -> KafkaConsumer:
    return KafkaConsumer(*topics, bootstrap_servers=config.KAFKA_BOOTSTRAP, group_id=config.CONSUMER_GROUP,
                         enable_auto_commit=False, auto_offset_reset="earliest", **_auth())
