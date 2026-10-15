#!/usr/bin/env bash
# Back up a directory to a timestamped, checksummed .tar.gz archive.
#
# Usage: backup.sh SOURCE_DIR [DEST_DIR]
#   SOURCE_DIR  directory to back up
#   DEST_DIR    where the archive and its .sha256 file are written (default: current directory)
#
# Exit codes: 0 success, 1 runtime error, 2 usage error.
set -euo pipefail

usage() {
    echo "Usage: $(basename "$0") SOURCE_DIR [DEST_DIR]" >&2
    exit 2
}

die() {
    echo "error: $*" >&2
    exit 1
}

[[ $# -ge 1 && $# -le 2 ]] || usage

src=${1%/}
dest=${2:-.}

[[ -d "$src" ]] || die "source directory '$src' does not exist"

# An empty source still produces a valid archive, but it is almost always a mistake.
if [[ -z "$(ls -A "$src")" ]]; then
    echo "warning: '$src' is empty; the archive will contain no files" >&2
fi

mkdir -p "$dest"

# UTC, sortable, and safe in file names on Linux and Windows (no colons).
timestamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
name="$(basename "$src")_${timestamp}.tar.gz"
archive="$dest/$name"

[[ ! -e "$archive" ]] || die "'$archive' already exists; wait a second and run again"

# -C keeps member paths relative ("dir/file"), never absolute.
tar -czf "$archive" -C "$(dirname "$src")" "$(basename "$src")"

# The checksum file uses a relative name so it can be verified wherever the pair is copied.
(cd "$dest" && sha256sum "$name" > "$name.sha256")

echo "backup:   $archive"
echo "checksum: $archive.sha256"
