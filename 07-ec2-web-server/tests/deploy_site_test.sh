#!/usr/bin/env bash
# End-to-end tests for deploy_site.sh on a real Ubuntu machine. They recreate my lab failure (nginx
# holding port 80, so apache2 will not start) and prove the script fixes it.
#
# These tests install packages and stop services, so they only run on a throwaway machine such as a
# CI runner: sudo ALLOW_SYSTEM_CHANGES=1 bash tests/deploy_site_test.sh
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
deploy="$here/../scripts/deploy_site.sh"
site="$here/../site"
title="Static site on Amazon EC2"

[[ ${ALLOW_SYSTEM_CHANGES:-} == 1 ]] || { echo "refusing to run: set ALLOW_SYSTEM_CHANGES=1 on a throwaway machine" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 2; }
[[ -d /run/systemd/system ]] || { echo "needs systemd" >&2; exit 2; }

pass=0
ok() { pass=$((pass + 1)); echo "ok $pass - $*"; }
fail() { echo "not ok - $*" >&2; exit 1; }
out=$(mktemp)
trap 'rm -f "$out"; [[ -n ${http_pid:-} ]] && kill "$http_pid" 2> /dev/null; true' EXIT

# Setup: the lab's starting point. Both servers installed, nginx running on port 80, apache2 stopped.
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx apache2 curl > /dev/null 2>&1 || true   # apache2's own start may fail here
systemctl stop apache2 2> /dev/null || true
systemctl enable --now nginx > /dev/null 2>&1

# 1. The lab failure: apache2 cannot start while nginx holds port 80.
if systemctl start apache2 2> /dev/null; then
    fail "apache2 started even though nginx holds port 80"
fi
reason=$(journalctl -u apache2 --no-pager -n 20 | grep -o '(98)Address already in use.*' | tail -n 1)
[[ -n "$reason" ]] || fail "apache2 failed for a reason other than the port: $(journalctl -u apache2 --no-pager -n 5)"
ok "apache2 fails to start while nginx holds port 80, as in the lab: $reason"

# 2. The script frees the port, then publishes and serves the site.
bash "$deploy" "$site" > "$out" 2>&1 || fail "deploy failed: $(cat "$out")"
grep -q "port 80 is held by nginx: stopping and disabling it" "$out" || fail "deploy did not report retiring nginx"
ok "deploy_site.sh retires nginx and publishes the site"

# 3. nginx is stopped and disabled, so it cannot take the port back at the next boot.
[[ $(systemctl is-active nginx || true) == inactive ]] || fail "nginx is still running"
[[ $(systemctl is-enabled nginx || true) == disabled ]] || fail "nginx is still enabled and would return after a reboot"
[[ $(systemctl is-active apache2) == active && $(systemctl is-enabled apache2) == enabled ]] || fail "apache2 is not active and enabled"
ok "nginx is stopped and disabled; apache2 is active and enabled"

# 4. The page is served on port 80.
curl -fsS http://127.0.0.1/ | grep -qF "<title>$title</title>" || fail "the site is not served on port 80"
ok "http://127.0.0.1/ serves the page"

# 5. The document root is read-only for Apache: root owns it, directories 755, files 644.
bad=$(find /var/www/html \( ! -user root -o \( -type d ! -perm 0755 \) -o \( -type f ! -perm 0644 \) \) -print | head -n 3)
[[ -z "$bad" ]] || fail "wrong owner or mode on: $bad"
ok "the document root is owned by root, directories 755, files 644"

# 6. Running it again changes nothing and still succeeds.
bash "$deploy" "$site" > "$out" 2>&1 || fail "second run failed: $(cat "$out")"
if grep -q "stopping and disabling" "$out"; then fail "second run tried to retire a server again"; fi
ok "a second run succeeds without changes"

# 7. A process the script does not know is never killed: it stops with exit code 3 and names it.
systemctl stop apache2
python3 -m http.server 80 --bind 0.0.0.0 > /dev/null 2>&1 &
http_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do ss -Hltn 'sport = :80' | grep -q . && break; sleep 0.5; done
set +e
bash "$deploy" "$site" > "$out" 2>&1
code=$?
set -e
[[ $code -eq 3 ]] || fail "expected exit code 3 with an unknown process on port 80, got $code: $(cat "$out")"
grep -q "held by 'python3'" "$out" || fail "the error does not name the process: $(cat "$out")"
kill "$http_pid"; wait "$http_pid" 2> /dev/null || true; http_pid=
ok "an unknown process on port 80 stops the script with exit code 3, and is left running"

# 8. Usage errors exit with code 2.
set +e
bash "$deploy" /nonexistent > /dev/null 2>&1
code=$?
set -e
[[ $code -eq 2 ]] || fail "a missing site folder should exit with code 2, got $code"
ok "a missing site folder is a usage error (exit 2)"

# Leave the machine serving the site.
bash "$deploy" "$site" > /dev/null
echo "all $pass tests passed"
