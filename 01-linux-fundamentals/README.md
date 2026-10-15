# 01 | Linux Fundamentals

**Lab date:** 26 February 2026 | **Environment:** Amazon Linux on an EC2 instance in the programme's training account | **Status:** rebuilt and tested

## The task, in my own words

Working over SSH on a Linux server: create a working folder and a text file from the command line, confirm the server can reach the internet, then write a shell script that backs up a folder into a timestamped archive, and prove the backup can be restored.

## What I did in the lab

The original session, transcribed from my screenshots (the server's public IP is removed):

```console
$ cd Sakariyau_Oseni-TeSA
$ mkdir tesa-lab-Sakariyau_Oseni
$ echo "Oseni is part of the contestant for TeSA cohort V" > tesa-file.txt

$ ping 8.8.8.8
64 bytes from 8.8.8.8: icmp_seq=1 ttl=112 time=0.742 ms
...
8 packets transmitted, 8 received, 0% packet loss, time 7115ms
rtt min/avg/max/mdev = 0.742/1.070/1.909/0.366 ms

$ nano Oseni_backup.sh && chmod +x Oseni_backup.sh && ./Oseni_backup.sh
Starting backup for 'tesa-lab-Sakariyau_Oseni'...
  adding: tesa-lab-Sakariyau_Oseni/ (stored 0%)
Success! Backup saved as: tesa-lab-Sakariyau_Oseni_2026-02-26_20-55-52.zip

$ unzip tesa-lab-Sakariyau_Oseni_2026-02-26_20-55-52.zip -d restored-tesa-lab-Sakariyau_Oseni
   creating: restored-tesa-lab-Sakariyau_Oseni/tesa-lab-Sakariyau_Oseni/
```

The original script hard-coded the folder name, built a `YYYY-MM-DD_HH-MM-SS` timestamp with `date`, checked the folder existed with `[ -d ]`, and ran `zip -r`.

## The rebuilt solution

| File | What it does |
|---|---|
| [`scripts/backup.sh`](scripts/backup.sh) | Archives any folder to `NAME_<UTC timestamp>.tar.gz` and writes a SHA-256 checksum beside it |
| [`scripts/restore.sh`](scripts/restore.sh) | Verifies the checksum first, then restores into an empty or new folder, never over existing data |
| [`tests/backup_restore_test.sh`](tests/backup_restore_test.sh) | Seven end-to-end tests, run in CI on every push |

Example run:

```console
$ ./scripts/backup.sh ~/tesa-lab ~/backups
backup:   /home/ec2-user/backups/tesa-lab_2026-10-15T01-52-07Z.tar.gz
checksum: /home/ec2-user/backups/tesa-lab_2026-10-15T01-52-07Z.tar.gz.sha256

$ ./scripts/restore.sh ~/backups/tesa-lab_2026-10-15T01-52-07Z.tar.gz ~/restored
restored into: /home/ec2-user/restored
```

### How it is tested

```console
$ bash tests/backup_restore_test.sh
ok 1 - backup creates a timestamped archive and a .sha256 file
ok 2 - restore reproduces the source byte for byte
ok 3 - restore refuses to write into a non-empty directory
ok 4 - a tampered archive fails the checksum and nothing is extracted
ok 5 - backing up a missing folder fails with exit code 1
ok 6 - missing arguments are a usage error (exit 2)
ok 7 - an empty source produces a warning
all 7 tests passed
```

Every script also passes [ShellCheck](https://www.shellcheck.net/). The [`shell` workflow](../.github/workflows/shell.yml) runs both checks on every push and pull request.

## Mistakes I fixed

1. **The backup proved nothing.** The folder I backed up was empty (`stored 0%`, a 200-byte zip), so the restore only showed that an empty folder comes back empty. The tests now use real files, including a nested folder and a name with a space, and compare the restored tree byte for byte with `diff -r`.
2. **The failure path was unfinished.** My screenshot stops at `else`. The scripts now stop on any error (`set -euo pipefail`), print errors to stderr, and use distinct exit codes: 1 for runtime errors, 2 for usage errors.
3. **Nothing checked the archive's integrity.** A corrupted or altered backup would have been restored silently. A SHA-256 checksum is now written at backup time and verified before anything is extracted.
4. **A restore could overwrite live data.** Unzipping into an existing folder mixes old and new files. `restore.sh` refuses any target that is not empty.
5. **Hard-coded and ambiguous names.** The folder name was fixed in the script, and the timestamp used the server's local time. Both scripts now take arguments, and timestamps are UTC (`2026-10-15T01-52-07Z`), so they sort correctly and cannot collide across time zones.
6. **A tool that is not always installed.** `zip` is missing from many minimal Linux images, while `tar` and `gzip` ship with every distribution.
7. **Script names did not match.** I ran `Oseni_backup.sh`, but the editor showed `backup.sh`. Each script now has one name and a usage line.

## Lab vs production

| Concern | In the lab | In production | Well-Architected pillar |
|---|---|---|---|
| Where backups live | The same disk as the data | Off the server: an S3 bucket with versioning and encryption, and Object Lock so ransomware cannot delete them | Reliability, Security |
| When backups run | By hand | On a schedule (a systemd timer or cron), or AWS Backup for whole-volume snapshots | Operational Excellence |
| Proof they work | None | Checksums on every backup, plus a scheduled test restore | Reliability |
| How long they are kept | Forever, by accident | Lifecycle rules: recent copies in S3, older ones moved to Glacier, then deleted | Cost Optimization |
| Knowing when one fails | Nobody would know | A non-zero exit code raises an alarm (for example, a CloudWatch alarm on a metric the job publishes) | Operational Excellence |
| Access | My login user | A least-privilege IAM role on the server; no access keys stored on disk | Security |
| Efficiency | A full copy every run | Incremental backups (for example, restic) that store only what changed | Performance Efficiency, Sustainability |

## What I learned

- A backup is only as good as its last tested restore.
- Small scripts deserve the same discipline as large programs: strict mode, clear errors, exit codes, and tests.
- A successful `ping 8.8.8.8` from a cloud server proves outbound routing to the internet. It says nothing about inbound access, which security groups and network ACLs control separately, and because it targets an IP address it does not test DNS.
