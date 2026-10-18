#!/bin/bash
# EC2 user data for the test host: runs once, as root, at first boot. Output: /var/log/cloud-init-output.log
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 python3-venv unzip
snap install aws-cli --classic
systemctl enable --now docker
touch /var/run/paygate-host-ready
