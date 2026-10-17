#!/usr/bin/env bash
# Smoke test for the deployed site: HTTPS works, HTTP is redirected, a missing page is a proper 404,
# security headers are set, and the bucket refuses every request that does not come through CloudFront.
#
#   bash tests/smoke_test.sh                                  # reads the addresses from terraform output
#   bash tests/smoke_test.sh https://dxxxx.cloudfront.net BUCKET.s3.eu-west-1.amazonaws.com
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -eq 2 ]]; then
  site_url="$1"
  bucket_host="$2"
else
  site_url="$(terraform -chdir="$here/../terraform" output -raw site_url)"
  bucket_host="$(terraform -chdir="$here/../terraform" output -raw bucket_regional_domain_name)"
fi
site_host="${site_url#https://}"

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
status() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

body="$(curl -s --max-time 20 "$site_url/")"
check "home page over HTTPS returns 200" 200 "$(status "$site_url/")"
check "home page is this site's page" yes "$(grep -q '<title>Private S3 site behind CloudFront</title>' <<<"$body" && echo yes || echo no)"

check "plain HTTP is redirected (301)" 301 "$(status "http://$site_host/")"
check "the redirect points to HTTPS" "https://$site_host/" \
  "$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 20 "http://$site_host/")"

missing="$site_url/no-such-page-$RANDOM"
check "a missing page returns 404" 404 "$(status "$missing")"
check "a missing page shows the error page" yes \
  "$(curl -s --max-time 20 "$missing" | grep -q 'Page not found' && echo yes || echo no)"

headers="$(curl -s -D - -o /dev/null --max-time 20 "$site_url/" | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
check "Strict-Transport-Security is set" yes "$(grep -q '^strict-transport-security:' <<<"$headers" && echo yes || echo no)"
check "X-Content-Type-Options is nosniff" yes "$(grep -q '^x-content-type-options: nosniff' <<<"$headers" && echo yes || echo no)"
check "X-Frame-Options is set" yes "$(grep -q '^x-frame-options:' <<<"$headers" && echo yes || echo no)"

check "the bucket refuses a direct HTTPS request (403)" 403 "$(status "https://$bucket_host/index.html")"
check "the bucket refuses a direct HTTP request (403)" 403 "$(status "http://$bucket_host/index.html")"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
