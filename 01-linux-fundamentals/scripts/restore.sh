#!/usr/bin/env bash
# Verify a backup made by backup.sh and restore it into an empty directory.
#
# Usage: restore.sh ARCHIVE TARGET_DIR
#   ARCHIVE     a .tar.gz produced by backup.sh (its .sha256 file is checked if present)
#   TARGET_DIR  directory to restore into; created if missing, must be empty if it exists
#
# Exit codes: 0 success, 1 runtime error (including a failed checksum), 2 usage error.
set -euo pipefail

usage() {
    echo "Usage: $(basename "$0") ARCHIVE TARGET_DIR" >&2
    exit 2
}

die() {
    echo "error: $*" >&2
    exit 1
}

[[ $# -eq 2 ]] || usage

archive=$1
target=$2

[[ -f "$archive" ]] || die "archive '$archive' does not exist"

checksum="$archive.sha256"
if [[ -f "$checksum" ]]; then
    (cd "$(dirname "$archive")" && sha256sum --check --quiet "$(basename "$checksum")" >&2) \
        || die "checksum mismatch: '$archive' is corrupted or was modified"
else
    echo "warning: no checksum file next to '$archive'; restoring without verification" >&2
fi

# Never restore over existing data.
if [[ -e "$target" ]]; then
    [[ -d "$target" ]] || die "'$target' exists and is not a directory"
    [[ -z "$(ls -A "$target")" ]] || die "'$target' is not empty; choose an empty or new directory"
fi
mkdir -p "$target"

tar -xzf "$archive" -C "$target"

echo "restored into: $target"
