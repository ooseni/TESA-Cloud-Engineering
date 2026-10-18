#!/usr/bin/env bash
# Checks what each pipeline role can and cannot do, with the IAM policy simulator, plus the trust policies
# and the state bucket's settings. Nothing is created or changed.
# Needs the AWS CLI, the GitHub CLI and an applied bootstrap/ folder.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tf() { terraform -chdir="$here/../bootstrap" output -raw "$1"; }
region="$(tf region)"
bucket="$(tf state_bucket)"
plan_role="$(tf plan_role_arn)"
apply_role="$(tf apply_role_arn)"
state="arn:aws:s3:::$bucket/13-iac-cicd/stack.tfstate"
lock="$state.tflock"
# the subject prefix GitHub actually puts in this repository's tokens
prefix="$(gh api repos/ooseni/TESA-Cloud-Engineering/actions/oidc/customization/sub --jq .sub_claim_prefix)"

passed=0
failed=0
check() {
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s\n' "$1"; passed=$((passed + 1));
  else printf 'FAIL  %s (expected %s, got %s)\n' "$1" "$2" "$3"; failed=$((failed + 1)); fi
}
# simulate ROLE ACTION RESOURCE [REGION]: allowed, implicitDeny or explicitDeny
simulate() {
  aws iam simulate-principal-policy --policy-source-arn "$1" --action-names "$2" --resource-arns "$3" \
    --context-entries "ContextKeyName=aws:RequestedRegion,ContextKeyValues=${4:-$region},ContextKeyType=string" \
    --query 'EvaluationResults[0].EvalDecision' --output text
}
subject() {
  aws iam get-role --role-name "${1##*/}" --output text \
    --query 'Role.AssumeRolePolicyDocument.Statement[0].Condition.StringEquals."token.actions.githubusercontent.com:sub"'
}

# ---- the plan role: read the state and the account, take the lock, change nothing
check "plan role can read the state" allowed "$(simulate "$plan_role" s3:GetObject "$state")"
check "plan role can take the state lock" allowed "$(simulate "$plan_role" s3:PutObject "$lock")"
check "plan role can describe EC2 resources" allowed "$(simulate "$plan_role" ec2:DescribeInstances '*')"
check "plan role cannot write the state" implicitDeny "$(simulate "$plan_role" s3:PutObject "$state")"
check "plan role cannot launch an instance" implicitDeny "$(simulate "$plan_role" ec2:RunInstances '*')"

# ---- the apply role: the stack's resources, in one Region, and nothing else
check "apply role can write the state" allowed "$(simulate "$apply_role" s3:PutObject "$state")"
check "apply role can launch an instance in $region" allowed "$(simulate "$apply_role" ec2:RunInstances '*')"
check "apply role cannot launch an instance in us-east-1" implicitDeny \
  "$(simulate "$apply_role" ec2:RunInstances '*' us-east-1)"
check "apply role cannot create IAM roles" implicitDeny "$(simulate "$apply_role" iam:CreateRole '*')"
check "apply role cannot delete the state" implicitDeny "$(simulate "$apply_role" s3:DeleteObject "$state")"
check "apply role cannot read other objects in the bucket" implicitDeny \
  "$(simulate "$apply_role" s3:GetObject "arn:aws:s3:::$bucket/other/terraform.tfstate")"

# ---- who may assume each role
check "only pull request runs of this repository can assume the plan role" "$prefix:pull_request" \
  "$(subject "$plan_role")"
check "only runs on main of this repository can assume the apply role" "$prefix:ref:refs/heads/main" \
  "$(subject "$apply_role")"

# ---- the state bucket
check "the state bucket blocks all public access" True \
  "$(aws s3api get-public-access-block --bucket "$bucket" --output text --query 'PublicAccessBlockConfiguration.
      [BlockPublicAcls && IgnorePublicAcls && BlockPublicPolicy && RestrictPublicBuckets] | [0]')"
check "the state bucket keeps every version" Enabled \
  "$(aws s3api get-bucket-versioning --bucket "$bucket" --query Status --output text)"
check "the state bucket refuses requests without TLS" yes \
  "$(aws s3api get-bucket-policy --bucket "$bucket" --query Policy --output text \
      | grep -q '"aws:SecureTransport":"false"' && echo yes || echo no)"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ "$failed" -eq 0 ]]
