#!/usr/bin/env bash
# Checks the stack the pipeline deployed: from the internet, from the AWS API and in the state bucket.
# The state is remote, so the instance is found by its Name tag. Needs the AWS CLI and an applied
# bootstrap/ folder (for the bucket's name).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tf() { terraform -chdir="$here/../bootstrap" output -raw "$1"; }
region="$(tf region)"
bucket="$(tf state_bucket)"
key="13-iac-cicd/stack.tfstate"

passed=0
failed=0
check() {
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s\n' "$1"; passed=$((passed + 1));
  else printf 'FAIL  %s (expected %s, got %s)\n' "$1" "$2" "$3"; failed=$((failed + 1)); fi
}
describe() {
  aws ec2 describe-instances --region "$region" --instance-ids "$instance_id" \
    --query "Reservations[0].Instances[0].$1" --output text
}

instance_id="$(aws ec2 describe-instances --region "$region" --output text \
  --filters Name=tag:Name,Values=tesa-m13-web Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].InstanceId')"
check "exactly one web server is running" 1 "$(wc -w <<<"$instance_id" | tr -d ' ')"
ip="$(describe PublicIpAddress)"

# ---- from the internet
check "the page is served over HTTP (200)" 200 \
  "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$ip/" || true)"
page="$(curl -s --max-time 10 "http://$ip/" || true)"
check "the page is the one the pipeline deployed" yes \
  "$(grep -q '<title>Deployed by the pipeline</title>' <<<"$page" && echo yes || echo no)"
check "port 22 does not answer" closed \
  "$(timeout 5 bash -c "exec 3<>/dev/tcp/$ip/22" 2>/dev/null && echo open || echo closed)"

# ---- from the AWS API
check "the instance has no SSH key pair" None "$(describe KeyName)"
check "the instance has no IAM role" None "$(describe IamInstanceProfile.Arn)"
check "the metadata service requires IMDSv2 tokens" required "$(describe MetadataOptions.HttpTokens)"
volume="$(describe 'BlockDeviceMappings[0].Ebs.VolumeId')"
check "the root disk is encrypted" True \
  "$(aws ec2 describe-volumes --region "$region" --volume-ids "$volume" --query 'Volumes[0].Encrypted' --output text)"
check "the instance is tagged as managed by the pipeline" "Terraform, GitHub Actions" \
  "$(describe "Tags[?Key=='ManagedBy'].Value | [0]")"

# ---- the remote state
check "the state is in the state bucket" yes \
  "$(aws s3api head-object --bucket "$bucket" --key "$key" >/dev/null 2>&1 && echo yes || echo no)"
check "the state lock was released" no \
  "$(aws s3api head-object --bucket "$bucket" --key "$key.tflock" >/dev/null 2>&1 && echo yes || echo no)"
state="$(aws s3 cp "s3://$bucket/$key" -)"
check "the state names the running instance" yes \
  "$(grep -q "\"$instance_id\"" <<<"$state" && echo yes || echo no)"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ "$failed" -eq 0 ]]
