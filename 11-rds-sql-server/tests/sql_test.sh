#!/usr/bin/env bash
# Runs the module's SQL against a real SQL Server and checks the results: a container in CI, or the RDS
# instance through an SSM port-forwarding session (see tests/rds_test.sh).
#
# Environment:
#   DB_HOST            host,port as seen from this machine (default 127.0.0.1,1433)
#   DB_ADMIN_USER      the admin login: sa in a container, the master user on RDS
#   DB_ADMIN_PASSWORD  its password
#   APP_PASSWORD       the password to give the squad_app login
#   EXPECT_FORCED_TLS  set to 1 on RDS: also check that the server encrypts a connection the client did not
#                      ask to encrypt (rds.force_ssl)
#   SQLCMD_IMAGE       the image whose sqlcmd is used (default: the SQL Server 2022 image used in CI)
# Passwords reach sqlcmd only through environment variables, never on a command line.
set -euo pipefail

: "${DB_ADMIN_USER:?set DB_ADMIN_USER}" "${DB_ADMIN_PASSWORD:?set DB_ADMIN_PASSWORD}" "${APP_PASSWORD:?set APP_PASSWORD}"
host="${DB_HOST:-127.0.0.1,1433}"
image="${SQLCMD_IMAGE:-mcr.microsoft.com/mssql/server:2022-CU26-ubuntu-22.04}"
sql_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../sql" && pwd)"
export APP_PASSWORD

# sqlcmd LOGIN PASSWORD [sqlcmd options...]
#   -C trusts the server certificate: the CI container's is self-signed, and through the tunnel the host
#   name is 127.0.0.1, which no certificate can match. -f 65001 reads the scripts as UTF-8.
#   -l 30 and -t 120 stop a dead connection or a stuck query from hanging the tests.
sqlcmd() {
  local user="$1"
  SQLCMDPASSWORD="$2" docker run --rm -i --network host -v "$sql_dir:/sql:ro" -e SQLCMDPASSWORD -e APP_PASSWORD \
    --entrypoint /opt/mssql-tools18/bin/sqlcmd "$image" -S "$host" -U "$user" -C -b -f 65001 -l 30 -t 120 "${@:3}"
}
admin() { sqlcmd "$DB_ADMIN_USER" "$DB_ADMIN_PASSWORD" "$@"; }
app() { sqlcmd squad_app "$APP_PASSWORD" -d squad_planner "$@"; }
# value WHO "query" [sqlcmd options...]: the first column of the first row
value() {
  local who="$1" query="$2"
  "$who" -h -1 -W "${@:3}" -Q "SET NOCOUNT ON; $query" | head -n 1 | tr -d '\r'
}

passed=0
failed=0
check() {   # check "description" "expected" "actual"
  if [[ "$2" == "$3" ]]; then
    printf 'PASS  %s\n' "$1"
    passed=$((passed + 1))
  else
    printf 'FAIL  %s (expected %s, got %s)\n' "$1" "$2" "$3"
    failed=$((failed + 1))
  fi
}
# refused WHO "statement" "text the error must contain": the statement must fail, for the expected reason
refused() {
  local out
  if out="$("$1" -Q "$2" 2>&1)"; then echo "accepted"; elif grep -q "$3" <<<"$out"; then echo "refused"; else
    echo "failed differently: $(head -n 1 <<<"$out")"; fi
}
run_all() {
  for f in 01_database.sql 02_schema.sql 03_seed.sql 04_app_access.sql; do admin -i "/sql/$f" >/dev/null; done
}

run_all
check "the scripts run" 6 "$(value admin "SELECT COUNT(*) FROM squad_planner.fantasy.target_squad;")"
run_all
check "the scripts run again without duplicating anything" 6 \
  "$(value admin "SELECT COUNT(*) FROM squad_planner.fantasy.target_squad;")"
check "a name with a non-English letter is stored intact" 1 \
  "$(value admin "SELECT COUNT(*) FROM squad_planner.fantasy.target_squad WHERE player_name = N'Martin Ødegaard';")"

insert="INSERT INTO squad_planner.fantasy.target_squad (player_name, position, club, price_millions, total_points) VALUES"
check "an unknown position is refused" refused \
  "$(refused admin "$insert (N'Test Player', 'Striker', N'Test FC', 6.0, 10);" ck_target_squad_position)"
check "a price below 3.5 is refused" refused \
  "$(refused admin "$insert (N'Test Player', 'Forward', N'Test FC', 2.0, 10);" ck_target_squad_price)"
check "negative points are refused" refused \
  "$(refused admin "$insert (N'Test Player', 'Forward', N'Test FC', 6.0, -1);" ck_target_squad_points)"
check "the same player at the same club twice is refused" refused \
  "$(refused admin "$insert (N'Bukayo Saka', 'Midfielder', N'Arsenal', 9.0, 1);" uq_target_squad_player)"

check "the app login can read the squad" 6 "$(value app "SELECT COUNT(*) FROM fantasy.target_squad;")"
app -Q "$insert (N'Test Player', 'Forward', N'Test FC', 6.0, 10);" >/dev/null
check "the app login can add a player" 1 \
  "$(value admin "SELECT COUNT(*) FROM squad_planner.fantasy.target_squad WHERE player_name = N'Test Player';")"
check "the app login cannot delete" refused \
  "$(refused app "DELETE FROM fantasy.target_squad WHERE player_name = N'Test Player';" "permission was denied")"
check "the app login cannot create tables" refused \
  "$(refused app "CREATE TABLE fantasy.not_allowed (id INT);" "permission denied")"
admin -Q "DELETE FROM squad_planner.fantasy.target_squad WHERE player_name = N'Test Player';" >/dev/null

check "the best value report puts Ollie Watkins first" "Ollie Watkins" \
  "$(admin -h -1 -W -s '|' -i /sql/05_best_value.sql | grep -v '^Changed database context' | head -n 1 | cut -d '|' -f 1)"
check "this connection is encrypted" TRUE \
  "$(value admin "SELECT encrypt_option FROM sys.dm_exec_connections WHERE session_id = @@SPID;")"
if [[ "${EXPECT_FORCED_TLS:-0}" == 1 ]]; then
  check "the server encrypts even when the client does not ask (rds.force_ssl)" TRUE \
    "$(value admin "SELECT encrypt_option FROM sys.dm_exec_connections WHERE session_id = @@SPID;" -No)"
fi

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
