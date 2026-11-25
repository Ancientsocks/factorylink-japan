#!/usr/bin/env bash
set -euo pipefail

schedule="${BACKUP_CRON_SCHEDULE:-15 1 * * *}"
[[ "$schedule" =~ ^[0-9*/,-]+[[:space:]]+[0-9*/,-]+[[:space:]]+[0-9*/,-]+[[:space:]]+[0-9*/,-]+[[:space:]]+[0-9*/,-]+$ ]] || {
  echo "BACKUP_CRON_SCHEDULE must contain five numeric cron fields." >&2
  exit 1
}

job="/bin/sh -c 'set -a; . /run/secrets/backup_env; set +a; exec /usr/bin/env bash /app/scripts/backup/production-backup.sh'"
printf '%s %s >> /proc/1/fd/1 2>&1\n' "$schedule" "$job" > /etc/crontabs/backup
exec crond -f -l 8
