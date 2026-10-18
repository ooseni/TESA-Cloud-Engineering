#!/usr/bin/env bash
# Runs on the test host, as root, through Systems Manager: starts the demo's containers against the real
# DynamoDB table and Amazon MSK (compose.aws.yaml), then runs the whole test suite.
# Run Command keeps only the first 24,000 characters of output, so the set-up goes to setup.log and only
# the test results are printed.
# Usage: host_run.sh REGION TABLE BOOTSTRAP_BROKERS
set -euo pipefail
cd "$(dirname "$0")"

export AWS_REGION="$1" TABLE_NAME="$2" KAFKA_BOOTSTRAP="$3"
export COMPOSE_FILE=compose.yaml:compose.aws.yaml

{
  docker compose down --volumes --remove-orphans
  docker compose build --quiet
  docker compose up --detach --no-deps --wait --quiet-pull sor vendor
  docker compose run --rm --no-deps setup
  docker compose up --detach --no-deps --wait gateway requery consumer
  python3 -m venv .venv
  .venv/bin/pip install --quiet --disable-pip-version-check -r requirements-test.txt
} > setup.log 2>&1 || { tail -40 setup.log; exit 1; }

# TEST_DYNAMODB_ENDPOINT is empty: the tests use the real table, with the instance role's credentials
export REQUIRE_DEMO=1 TEST_DYNAMODB_ENDPOINT="" TEST_TABLE="$TABLE_NAME" TEST_KAFKA_BOOTSTRAP="$KAFKA_BOOTSTRAP"
export KAFKA_AUTH=iam
.venv/bin/python -m pytest -p no:cacheprovider -v 2>&1 | tee pytest.log | grep -E 'PASSED|FAILED|ERROR|passed|failed'
