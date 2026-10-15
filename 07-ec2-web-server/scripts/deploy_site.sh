#!/usr/bin/env bash
# Publish a static site with Apache on Ubuntu, safely and repeatably.
#
# Built from my EC2 lab, where Apache would not start because nginx already held port 80 and every
# Amazon Linux command (yum, httpd, ec2-user, group apache) failed on Ubuntu. This script:
#   1. takes port 80 back from another web server, stopping it AND disabling it, so it cannot
#      win the race for the port again after a reboot; anything else on port 80 is an error;
#   2. installs Apache with apt (Ubuntu's package is apache2, not httpd);
#   3. publishes the site read-only: owned by root, directories 755, files 644;
#   4. checks Apache's configuration, then enables and starts it;
#   5. proves the page is served before reporting success.
# It is safe to run again, and it is written to run as EC2 user data at first boot.
#
# Usage: deploy_site.sh SITE_DIR [EXPECTED_TEXT]
#   SITE_DIR       folder with index.html and its files
#   EXPECTED_TEXT  text the served page must contain (default: the page's <title>)
#
# Exit codes: 0 site live, 1 runtime error, 2 usage error or not Ubuntu,
#             3 port 80 held by something this script will not stop.
set -euo pipefail

DOCROOT=${DOCROOT:-/var/www/html}
KNOWN_WEB_SERVERS="nginx lighttpd caddy httpd"   # services that may hold port 80 and can be retired

usage() {
    echo "Usage: $(basename "$0") SITE_DIR [EXPECTED_TEXT]" >&2
    exit 2
}

die() {
    echo "error: $*" >&2
    exit "${2:-1}"
}

log() { echo "deploy: $*"; }

[[ $# -ge 1 && $# -le 2 ]] || usage
site=${1%/}
[[ -f "$site/index.html" ]] || die "'$site' has no index.html" 2
[[ $EUID -eq 0 ]] || die "run as root (sudo), or as EC2 user data" 2
command -v apt-get > /dev/null || die "this script is for Ubuntu; on Amazon Linux the package and service are httpd (dnf install httpd)" 2

expected=${2:-$(sed -n 's:.*<title>\(.*\)</title>.*:\1:p' "$site/index.html" | head -n 1)}
[[ -n "$expected" ]] || die "no EXPECTED_TEXT given and index.html has no <title>" 2

# 1. Who holds port 80? ss reports the owning process for every listening socket. This comes first:
#    installing apache2 starts it, and that start fails if another server has the port.
holders=$(ss -Hltnp 'sport = :80' | grep -o 'users:(("[^"]*' | cut -d'"' -f2 | sort -u || true)
for proc in $holders; do
    case "$proc" in
        apache2) ;;                                     # already ours
        *)
            if [[ " $KNOWN_WEB_SERVERS " == *" $proc "* ]] && systemctl cat "$proc.service" > /dev/null 2>&1; then
                log "port 80 is held by $proc: stopping and disabling it"
                systemctl disable --now "$proc" 2> /dev/null   # stop now, and stay stopped after a reboot
            else
                die "port 80 is held by '$proc', which this script will not stop; free the port and run it again" 3
            fi
            ;;
    esac
done

# 2. Install Apache. apt-get rather than apt: apt's command-line interface is not stable for scripts.
if ! dpkg-query -W -f='${Status}' apache2 2> /dev/null | grep -q "install ok installed"; then
    log "installing apache2"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq apache2 > /dev/null
fi
command -v curl > /dev/null || { apt-get install -y -qq curl > /dev/null; }

# 3. Publish the site read-only. Apache runs as www-data and only needs to read.
log "publishing $site to $DOCROOT"
install -d -o root -g root -m 0755 "$DOCROOT"
cp -r "$site"/. "$DOCROOT"/
chown -R root:root "$DOCROOT"
find "$DOCROOT" -type d -exec chmod 0755 {} +
find "$DOCROOT" -type f -exec chmod 0644 {} +

# 4. Check the configuration before (re)starting, so a typo cannot take the site down.
apache2ctl -t 2> /dev/null || die "apache2 configuration test failed: run 'apache2ctl -t' for details"
systemctl enable --now apache2 > /dev/null 2>&1 || die "apache2 did not start: see 'systemctl status apache2' and 'journalctl -xeu apache2'"
systemctl reload apache2

# 5. Prove it: the page must be served on port 80 and contain the expected text.
for _ in 1 2 3 4 5; do
    page=$(curl -fsS --max-time 5 http://127.0.0.1/ 2> /dev/null || true)
    if grep -qF "$expected" <<< "$page"; then
        log "site is live: http://127.0.0.1/ serves \"$expected\""
        exit 0
    fi
    sleep 1
done
die "apache2 is running but http://127.0.0.1/ does not serve \"$expected\""
