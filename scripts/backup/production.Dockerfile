FROM alpine:3.22

RUN apk add --no-cache age aws-cli bash coreutils postgresql17-client tar tzdata \
    && addgroup -S -g 10001 backup \
    && adduser -S -D -H -u 10001 -G backup backup \
    && mkdir -p /app/scripts/backup /home/backup /etc/crontabs \
    && chown -R backup:backup /app /home/backup /etc/crontabs

COPY --chown=backup:backup scripts/backup/production-backup.sh /app/scripts/backup/production-backup.sh
COPY --chown=backup:backup scripts/backup/production-backup-scheduler.sh /usr/local/bin/production-backup-scheduler

RUN chmod 0555 /app/scripts/backup/production-backup.sh /usr/local/bin/production-backup-scheduler

ENV HOME=/home/backup
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/production-backup-scheduler"]
