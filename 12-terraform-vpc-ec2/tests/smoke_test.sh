#!/usr/bin/env bash
# Checks every hardening claim against the deployed instance: from the internet, from the AWS API, and from
# inside the instance through Systems Manager Run Command (no SSH involved anywhere).
# Needs the AWS CLI and an applied terraform/ folder.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tf() { terraform -chdir="$here/../terraform" output -raw "$1"; }
region="$(tf region)"
instance_id="$(tf instance_id)"
site_url="$(tf site_url)"
sg_id="$(tf security_group_id)"
ip="${site_url#http://}"

passed=0
failed=0
check() {
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s\n' "$1"; passed=$((passed + 1));
  else printf 'FAIL  %s (expected %s, got %s)\n' "$1" "$2" "$3"; failed=$((failed + 1)); fi
}
describe() {
  aws ec2 describe-instances --region "$region" --instance-ids "$instance_id" --query "Reservations[0].Instances[0].$1" --output text
}

# ---- from the internet; user data may still be installing nginx on a fresh instance
status=000
for _ in $(seq 1 30); do
  status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$site_url/" || true)"
  [[ "$status" == 200 ]] && break
  sleep 5
done
check "the page is served over HTTP (200)" 200 "$status"
check "the page is the one user data wrote" yes \
  "$(curl -s --max-time 10 "$site_url/" | grep -q '<title>Hardened EC2 web server</title>' && echo yes || echo no)"
check "port 22 does not answer" closed \
  "$(timeout 5 bash -c "exec 3<>/dev/tcp/$ip/22" 2>/dev/null && echo open || echo closed)"

# ---- from the AWS API
check "the instance has no SSH key pair" None "$(describe KeyName)"
check "the metadata service requires IMDSv2 tokens" required "$(describe MetadataOptions.HttpTokens)"
volume="$(describe 'BlockDeviceMappings[0].Ebs.VolumeId')"
check "the root disk is encrypted" True \
  "$(aws ec2 describe-volumes --region "$region" --volume-ids "$volume" --query 'Volumes[0].Encrypted' --output text)"
check "the root disk is gp3" gp3 \
  "$(aws ec2 describe-volumes --region "$region" --volume-ids "$volume" --query 'Volumes[0].VolumeType' --output text)"
# shellcheck disable=SC2016  # the backticks are JMESPath literals, not shell
check "no security group rule mentions port 22" 0 \
  "$(aws ec2 describe-security-group-rules --region "$region" --filters "Name=group-id,Values=$sg_id" \
      --query 'length(SecurityGroupRules[?FromPort==`22` || ToPort==`22`])' --output text)"

# ---- from inside the instance, through Systems Manager
ping=None
for _ in $(seq 1 24); do
  ping="$(aws ssm describe-instance-information --region "$region" \
    --filters "Key=InstanceIds,Values=$instance_id" --query 'InstanceInformationList[0].PingStatus' --output text)"
  [[ "$ping" == Online ]] && break
  sleep 5
done
check "the instance is online in Systems Manager" Online "$ping"

# One Run Command: nginx's state, then an IMDSv1 request (no token), which must be refused with 401.
command_id="$(aws ssm send-command --region "$region" --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript --comment "module 12 smoke test" \
  --parameters 'commands=["systemctl is-active nginx","curl -s -o /dev/null -w %{http_code} http://169.254.169.254/latest/meta-data/"]' \
  --query Command.CommandId --output text)"
aws ssm wait command-executed --region "$region" --command-id "$command_id" --instance-id "$instance_id" || true
output="$(aws ssm get-command-invocation --region "$region" --command-id "$command_id" --instance-id "$instance_id" \
  --query StandardOutputContent --output text)"
check "nginx is running (checked through Run Command)" active "$(sed -n 1p <<<"$output")"
check "an IMDSv1 request without a token is refused (401)" 401 "$(sed -n 2p <<<"$output" | tr -d '[:space:]')"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
