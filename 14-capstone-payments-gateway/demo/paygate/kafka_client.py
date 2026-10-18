"""Kafka clients. Locally the broker takes plain connections; on Amazon MSK they use TLS and IAM
authentication, with short-lived tokens signed from the caller's AWS credentials (no stored secret)."""
from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer

from . import config


def auth() -> dict:
    """Connection settings for the configured authentication: none locally, IAM on Amazon MSK."""
    if config.KAFKA_AUTH != "iam":
        return {}
    from aws_msk_iam_sasl_signer import MSKAuthTokenProvider
    from kafka.net.sasl.oauth import AbstractTokenProvider

    class MSKToken(AbstractTokenProvider):
        def token(self):
            return MSKAuthTokenProvider.generate_auth_token(config.AWS_REGION)[0]

    return {"security_protocol": "SASL_SSL", "sasl_mechanism": "OAUTHBEARER",
            "sasl_oauth_token_provider": MSKToken()}


def producer(bootstrap: str | None = None) -> KafkaProducer:
    # acks=all: a message counts as sent only when every in-sync replica has it.
    # One request in flight per connection keeps a payment's changes in order through retries.
    return KafkaProducer(bootstrap_servers=bootstrap or config.KAFKA_BOOTSTRAP, acks="all", retries=5,
                         max_in_flight_requests_per_connection=1, **auth())


def consumer(*topics: str, group: str | None = config.CONSUMER_GROUP, bootstrap: str | None = None,
             **kwargs) -> KafkaConsumer:
    return KafkaConsumer(*topics, bootstrap_servers=bootstrap or config.KAFKA_BOOTSTRAP, group_id=group,
                         enable_auto_commit=False, auto_offset_reset="earliest", **auth(), **kwargs)


def admin(bootstrap: str | None = None) -> KafkaAdminClient:
    return KafkaAdminClient(bootstrap_servers=bootstrap or config.KAFKA_BOOTSTRAP, **auth())
