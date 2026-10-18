#!/usr/bin/env bash
# Builds the two zips the run needs, in dist/ (not committed):
#   relay.zip  the Lambda function: the demo's paygate package and its Kafka libraries, built in the same
#              Python 3.12 image the demo uses, for Lambda's python3.12 runtime on x86_64
#   demo.zip   the demo folder plus host_run.sh, for the test host
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo="$here/../demo"
dist="$here/dist"
rm -rf "$dist"
mkdir -p "$dist/relay"

# the relay's libraries, at the versions the demo pins
mapfile -t libs < <(grep -E '^(kafka-python|aws-msk-iam-sasl-signer-python)==' "$demo/requirements.txt")
docker run --rm --user "$(id -u):$(id -g)" -v "$dist/relay:/out" python:3.12.14-slim \
  pip install --quiet --no-cache-dir --disable-pip-version-check --target /out "${libs[@]}"
cp -r "$demo/paygate" "$dist/relay/"

python3 - "$dist" "$demo" "$here/host_run.sh" <<'PY'
import sys, zipfile
from pathlib import Path

dist, demo, host_run = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
skip = ("__pycache__", ".venv", ".pytest_cache")

def add(zf, path, name):
    # a fixed date and mode, so the same files always make the same zip: Terraform then sees no change
    info = zipfile.ZipInfo(str(name), date_time=(1980, 1, 1, 0, 0, 0))
    info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, path.read_bytes())

def add_tree(zf, root):
    for f in sorted(root.rglob("*")):
        if f.is_file() and not any(part in skip for part in f.relative_to(root).parts):
            add(zf, f, f.relative_to(root).as_posix())

with zipfile.ZipFile(dist / "relay.zip", "w", zipfile.ZIP_DEFLATED) as zf:
    add_tree(zf, dist / "relay")
with zipfile.ZipFile(dist / "demo.zip", "w", zipfile.ZIP_DEFLATED) as zf:
    add_tree(zf, demo)
    add(zf, host_run, "host_run.sh")
for z in ("relay.zip", "demo.zip"):
    print(f"{z}: {(dist / z).stat().st_size // 1024} KB")
PY
