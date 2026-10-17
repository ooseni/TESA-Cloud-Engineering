#!/usr/bin/env bash
# Tests the deployed RDS instance end to end, from a workstation, with no public endpoint:
#   1. checks the network settings that keep the database private;
#   2. opens a Session Manager port-forwarding session through the access instance;
#   3. runs tests/sql_test.sh through it, with the passwords read from AWS Secrets Manager.
# Needs the AWS CLI, the Session Manager plugin, Docker and an applied terraform/ folder.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tf() { terraform -chdir="$here/../terraform" output -raw "$1"; }
region="$(tf region)"
db_address="$(tf db_address)"
db_port="$(tf db_port)"
instance_id="$(tf access_instance_id)"
db_sg="$(tf db_security_group_id)"
local_port="${LOCAL_PORT:-11433}"

passed=0
failed=0
check() {
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s\n' "$1"; passed=$((passed + 1));
  else printf 'FAIL  %s (expected %s, got %s)\n' "$1" "$2" "$3"; failed=$((failed + 1)); fi
}

# ---- the network keeps the database private
check "the instance is not publicly accessible" False \
  "$(aws rds describe-db-instances --region "$region" --db-instance-identifier tesa-m11-sqlserver \
      --query 'DBInstances[0].PubliclyAccessible' --output text)"
ip="$(getent hosts "$db_address" | awk '{print $1}')"
check "its DNS name resolves to a private address" yes "$([[ "$ip" =~ ^10\. ]] && echo yes || echo no)"
# shellcheck disable=SC2016  # the backticks are JMESPath literals, not shell
check "its security group admits no address range, only the access instance's group" 0 \
  "$(aws ec2 describe-security-group-rules --region "$region" --filters "Name=group-id,Values=$db_sg" \
      --query 'length(SecurityGroupRules[?!IsEgress && CidrIpv4 != `null`])' --output text)"
check "a direct connection from here fails" refused \
  "$(timeout 5 bash -c "exec 3<>/dev/tcp/$ip/$db_port" 2>/dev/null && echo connected || echo refused)"

# ---- a port-forwarding session through the access instance
if (exec 3<>"/dev/tcp/127.0.0.1/$local_port") 2>/dev/null; then
  echo "port $local_port is already in use (an old tunnel?); set LOCAL_PORT or close it first"
  exit 1
fi
# setsid gives the CLI and the plugin it starts their own process group, so the trap closes both
setsid aws ssm start-session --region "$region" --target "$instance_id" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "host=$db_address,portNumber=$db_port,localPortNumber=$local_port" >/dev/null &
session=$!
trap 'kill -- -"$session" 2>/dev/null || true' EXIT
tunnel=no
for _ in $(seq 1 30); do
  if (exec 3<>"/dev/tcp/127.0.0.1/$local_port") 2>/dev/null; then tunnel=yes; break; fi
  sleep 2
done
check "a Session Manager tunnel is open on 127.0.0.1:$local_port" yes "$tunnel"
if [[ $tunnel != yes ]]; then
  echo "no tunnel: is the Session Manager plugin installed, and is the access instance online in Systems Manager?"
  exit 1
fi

# ---- passwords from Secrets Manager, straight into environment variables
secret() { aws secretsmanager get-secret-value --region "$region" --secret-id "$1" --query SecretString --output text; }
master_json="$(secret "$(tf master_secret_arn)")"
DB_ADMIN_USER="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["username"])' <<<"$master_json")"
DB_ADMIN_PASSWORD="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["password"])' <<<"$master_json")"
APP_PASSWORD="$(secret "$(tf app_secret_arn)")"
unset master_json
export DB_ADMIN_USER DB_ADMIN_PASSWORD APP_PASSWORD
export DB_HOST="127.0.0.1,$local_port" EXPECT_FORCED_TLS=1

printf '\n'
sql_status=0
bash "$here/sql_test.sh" || sql_status=$?

printf '\nnetwork and access: %d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 && $sql_status -eq 0 ]]
