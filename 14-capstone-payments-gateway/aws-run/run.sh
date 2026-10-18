#!/usr/bin/env bash
# Runs the demo's test suite on AWS, after `terraform apply`: waits for the test host, has it download the
# bundle and run host_run.sh through Systems Manager Run Command, and prints the results.
# Needs the AWS CLI and an applied terraform/ folder.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tf() { terraform -chdir="$here/terraform" output -raw "$1"; }
region="$(tf region)"
host="$(tf host_instance_id)"
bucket="$(tf bundle_bucket)"
table="$(tf table_name)"
brokers="$(tf bootstrap_brokers)"

echo "waiting for the host to register with Systems Manager"
for _ in $(seq 1 60); do
  ping="$(aws ssm describe-instance-information --region "$region" --filters "Key=InstanceIds,Values=$host" \
    --query 'InstanceInformationList[0].PingStatus' --output text)"
  [[ "$ping" == Online ]] && break
  sleep 10
done
[[ "$ping" == Online ]] || { echo "the host never came online" >&2; exit 1; }

# Run Command uses /bin/sh, which is dash on Ubuntu: no pipefail here; host_run.sh runs under bash
script="set -eu
for _ in \$(seq 1 60); do [ -f /var/run/paygate-host-ready ] && break; sleep 10; done
rm -rf /opt/paygate && mkdir -p /opt/paygate && cd /opt/paygate
aws s3 cp s3://$bucket/demo.zip . --region $region --only-show-errors && unzip -q demo.zip
bash host_run.sh $region $table $brokers"
params="$(python3 -c 'import json, sys; print(json.dumps({"commands": sys.argv[1].splitlines(), "executionTimeout": ["3600"]}))' "$script")"

command_id="$(aws ssm send-command --region "$region" --instance-ids "$host" --document-name AWS-RunShellScript \
  --comment "paygate test run" --parameters "$params" --timeout-seconds 600 --query Command.CommandId --output text)"
echo "running the suite on $host (command $command_id)"

status=InProgress
while [[ "$status" == InProgress || "$status" == Pending || "$status" == Delayed ]]; do
  sleep 20
  status="$(aws ssm get-command-invocation --region "$region" --command-id "$command_id" --instance-id "$host" \
    --query Status --output text 2>/dev/null || echo Pending)"
done
aws ssm get-command-invocation --region "$region" --command-id "$command_id" --instance-id "$host" \
  --query '[StandardOutputContent, StandardErrorContent]' --output text
echo "command status: $status"
[[ "$status" == Success ]]
