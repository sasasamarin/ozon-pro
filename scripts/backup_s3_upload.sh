#!/usr/bin/env bash
# Заливает последний backup из /root/backups/auto/ в Selectel Object Storage (S3).
# Запускается ПОСЛЕ flowoi-backup.service (через systemd RequisitedBy).
#
# Конфиг: /etc/flowoi/s3.env (chmod 600). Поля:
#   S3_ENDPOINT       https://s3.ru-1.storage.selcloud.ru
#   S3_BUCKET         flowoi-backups
#   S3_ACCESS_KEY     ...
#   S3_SECRET_KEY     ...
#   S3_PREFIX         db/   (опционально, default = 'db/')
#
# Стратегия: грузим только файлы созданные за последние 6 часов
# (т.е. свежие — не пытаемся переливать старые при каждом запуске).
#
# Использует aws-cli v2 (apt install awscli или pip install).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/root/backups/auto}"
ENV_FILE="${S3_ENV:-/etc/flowoi/s3.env}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] s3-upload: $*"; }

if [[ ! -r "$ENV_FILE" ]]; then
    log "WARN: $ENV_FILE not found — S3 upload skipped (backup сделан локально)"
    exit 0
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${S3_ENDPOINT:?S3_ENDPOINT not set}"
: "${S3_BUCKET:?S3_BUCKET not set}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY not set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY not set}"
S3_PREFIX="${S3_PREFIX:-db/}"

if ! command -v aws &>/dev/null; then
    log "ERROR: aws CLI не установлен. apt-get install -y awscli"
    exit 2
fi

# Свежие файлы — за последние 6 часов (на случай если service запускается дважды в день)
mapfile -t FRESH < <(find "$BACKUP_DIR" -maxdepth 1 -name 'db_*.sql.gz' -mmin -360)
if [[ ${#FRESH[@]} -eq 0 ]]; then
    log "no fresh backups (<6h) — nothing to upload"
    exit 0
fi

export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY"

for f in "${FRESH[@]}"; do
    base=$(basename "$f")
    log "uploading $base → s3://${S3_BUCKET}/${S3_PREFIX}${base}"
    if aws --endpoint-url "$S3_ENDPOINT" s3 cp "$f" "s3://${S3_BUCKET}/${S3_PREFIX}${base}" \
         --no-progress --storage-class STANDARD 2>&1 | tail -2; then
        log "uploaded_ok $base"
    else
        log "ERROR uploading $base"
        exit 3
    fi
done

log "s3_upload_complete uploaded=${#FRESH[@]}"
