#!/usr/bin/env bash
# End-to-end tests for backup.sh and restore.sh. Run from anywhere: bash tests/backup_restore_test.sh
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
backup="$here/../scripts/backup.sh"
restore="$here/../scripts/restore.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

pass=0
ok() { pass=$((pass + 1)); echo "ok $pass - $*"; }
fail() { echo "not ok - $*" >&2; exit 1; }

# Fixture: real content this time, including a nested folder and a file name with a space.
mkdir -p "$work/tesa-lab/notes"
echo "TeSA cohort lab file" > "$work/tesa-lab/tesa-file.txt"
printf 'line one\nline two\n' > "$work/tesa-lab/notes/week 1.txt"

# 1. Backup creates an archive and a checksum.
bash "$backup" "$work/tesa-lab" "$work/backups" > /dev/null
archive=$(find "$work/backups" -name 'tesa-lab_*.tar.gz' | head -n 1)
[[ -n "$archive" && -f "$archive.sha256" ]] || fail "backup did not create an archive and checksum"
ok "backup creates a timestamped archive and a .sha256 file"

# 2. Restore reproduces the source exactly.
bash "$restore" "$archive" "$work/restored" > /dev/null
diff -r "$work/tesa-lab" "$work/restored/tesa-lab" || fail "restored tree differs from the source"
ok "restore reproduces the source byte for byte"

# 3. Restore refuses a non-empty target.
if bash "$restore" "$archive" "$work/restored" 2> /dev/null; then
    fail "restore overwrote a non-empty directory"
fi
ok "restore refuses to write into a non-empty directory"

# 4. A tampered archive is rejected before anything is extracted.
cp "$archive" "$work/tampered.tar.gz"
cp "$archive.sha256" "$work/tampered.tar.gz.sha256"
sed -i "s/$(basename "$archive")/tampered.tar.gz/" "$work/tampered.tar.gz.sha256"
printf 'x' >> "$work/tampered.tar.gz"
if bash "$restore" "$work/tampered.tar.gz" "$work/restored-tampered" 2> /dev/null; then
    fail "restore accepted a tampered archive"
fi
[[ ! -e "$work/restored-tampered" ]] || fail "restore extracted before verifying"
ok "a tampered archive fails the checksum and nothing is extracted"

# 5. Backup of a missing folder fails with exit code 1.
set +e
bash "$backup" "$work/does-not-exist" "$work/backups" 2> /dev/null
code=$?
set -e
[[ $code -eq 1 ]] || fail "missing source should exit 1, got $code"
ok "backing up a missing folder fails with exit code 1"

# 6. Wrong arguments are a usage error (exit 2).
set +e
bash "$backup" 2> /dev/null
code=$?
set -e
[[ $code -eq 2 ]] || fail "no arguments should exit 2, got $code"
ok "missing arguments are a usage error (exit 2)"

# 7. An empty source is allowed but warned about.
mkdir -p "$work/empty"
warning=$(bash "$backup" "$work/empty" "$work/backups-empty" 2>&1 > /dev/null)
[[ "$warning" == *"is empty"* ]] || fail "empty source was not warned about"
ok "an empty source produces a warning"

echo "all $pass tests passed"
