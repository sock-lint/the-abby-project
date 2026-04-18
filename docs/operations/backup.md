# Backup & Recovery Runbook

Scope: what to back up, how often, and how to restore. The app's durable
state lives in three places:

1. **Postgres** (`db` service) — authoritative for everything: users,
   projects, ledgers (money + coins), badges, inventory, quests, etc.
2. **Redis** (`redis` service) — Celery broker + cache + Instructables
   scrape cache. Not authoritative; can be rebuilt from Postgres + code.
3. **Media blobs** — project photos, homework proofs, user avatars.
   Stored locally on the `django` container in dev, or in **Ceph RGW**
   (`s3.neato.digital`) when `USE_S3_STORAGE=true`.

## TL;DR — minimum viable backup

Put this in a host cron (`crontab -e` on the deploy host, or a systemd
timer) — nightly Postgres dump + retention:

```bash
# /etc/cron.d/abby-backup
0 3 * * * root /opt/the-abby-project/scripts/backup.sh >> /var/log/abby-backup.log 2>&1
```

`scripts/backup.sh` (create it if missing):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/the-abby-project

STAMP=$(date +%Y%m%d-%H%M%S)
OUT=/var/backups/abby
mkdir -p "$OUT"

# 1. Postgres — logical dump via the running container
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-summerforge}" \
    "${POSTGRES_DB:-summerforge}" | gzip > "$OUT/db-$STAMP.sql.gz"

# 2. Redis — request a background save, then copy the RDB out
docker compose exec -T redis redis-cli BGSAVE
sleep 5
docker compose cp redis:/data/dump.rdb "$OUT/redis-$STAMP.rdb"

# 3. Retention: keep last 14 daily, plus the first of each month
find "$OUT" -name 'db-*.sql.gz' -mtime +14 \
    ! -name "db-$(date +%Y%m01)-*.sql.gz" -delete
find "$OUT" -name 'redis-*.rdb' -mtime +14 \
    ! -name "redis-$(date +%Y%m01)-*.rdb" -delete
```

Don't stop there — copy the backups off-box. Options in rough cost order:

- `rclone sync /var/backups/abby remote:abby-backups` to a different
  Ceph bucket or B2/S3 bucket.
- `rsync -az` to a different host on the LAN.
- Borg/restic to an off-site repo.

## Postgres

### Manual dump

```bash
# From the deploy host — all schemas, plain SQL
docker compose exec -T db pg_dump -U summerforge summerforge \
    | gzip > /tmp/backup-$(date +%s).sql.gz

# Custom format (smaller, parallel restore possible)
docker compose exec -T db pg_dump -Fc -U summerforge summerforge \
    > /tmp/backup-$(date +%s).dump
```

### Restore into a fresh environment

```bash
# Boot just db + redis on the target host
docker compose up -d db redis

# Wipe + recreate the target database
docker compose exec -T db psql -U summerforge postgres \
    -c "DROP DATABASE IF EXISTS summerforge;"
docker compose exec -T db psql -U summerforge postgres \
    -c "CREATE DATABASE summerforge OWNER summerforge;"

# Restore
gunzip -c /path/to/db-YYYYMMDD-HHMMSS.sql.gz \
    | docker compose exec -T db psql -U summerforge summerforge

# Sanity check
docker compose run --rm django python manage.py check
docker compose run --rm django python manage.py showmigrations --list | tail
```

### Point-in-time recovery

Out of scope for this runbook. If you need PITR, enable WAL archiving
on Postgres and ship WAL segments to object storage — that's a larger
change and should be paired with a restore drill.

## Redis

Redis is configured with `--appendonly yes` (see `docker-compose.yml`),
so the `redis_data` volume already contains an AOF that survives restarts.
For disaster recovery:

```bash
# Force an RDB snapshot on demand
docker compose exec -T redis redis-cli BGSAVE

# Copy the snapshot out
docker compose cp redis:/data/dump.rdb /var/backups/abby/redis-$(date +%s).rdb
```

Restore: stop redis, drop `dump.rdb` into the volume, start redis.

In practice, losing Redis is survivable — Celery will drop in-flight
tasks but the Beat schedule is stored in Postgres
(`django_celery_beat`), so re-scheduled runs still happen. The scrape
cache rebuilds on demand.

## Media blobs

### Local filesystem (dev, `USE_S3_STORAGE=false`)

Blobs live under the Django container's `MEDIA_ROOT`. Add the path to
your host-side filesystem backup (Borg/restic/rsync). The compose file
does **not** bind-mount `/app/media` by default; if you want blobs to
survive container rebuilds, either bind-mount it or switch to S3
(recommended — see below).

### Ceph RGW (production, `USE_S3_STORAGE=true`)

Two overlapping concerns:

1. **Versioning** — Enable bucket versioning on the Ceph side
   (`s3cmd setversioning s3://<bucket> enable` or the RGW admin API).
   CLAUDE.md calls out that `on_delete=CASCADE` on `Project` /
   `HomeworkSubmission` orphans blobs in storage; with versioning on,
   deletes create delete markers instead of purging bytes, so an
   orphan-cleanup script can be re-run safely.
2. **Cross-bucket replication** — If the Ceph cluster itself is the
   single failure domain, replicate the media bucket to a different
   provider with `rclone sync`:

   ```bash
   rclone sync ceph-rgw:abby-media b2:abby-media-dr \
       --fast-list --checkers 16 --transfers 8
   ```

   Run nightly, after the Postgres dump — a DB restore without the
   paired blobs will render with broken image URLs.

### Orphan cleanup

Not a backup concern per se, but related: the "Storage deletes" gotcha
in `CLAUDE.md` describes the orphan scenario. A management command to
sweep orphans is listed as future work in `docs/` — revisit when the
orphan rate is visible enough to matter (check the Ceph bucket size
growth vs. the sum of `ProjectPhoto.image` + `HomeworkProof.image` +
`User.avatar` row sizes).

## Restore drill

Run this end-to-end at least every 90 days. An untested backup is a
hope, not a backup.

1. Spin up a scratch VM or local Docker environment.
2. Restore the latest `db-*.sql.gz` into it (see "Restore" above).
3. Run `python manage.py check` and `python manage.py showmigrations`
   — both should pass/match production.
4. Smoke-test a login against the restored DB with a known child
   account.
5. If using S3, point the restored Django at a read-only Ceph IAM user
   with access to the media bucket and confirm a project photo renders
   in the Sketchbook page.
6. Record the drill in this file's changelog below (date + any issues).

## Changelog

- *(none yet — log the next restore drill here)*
