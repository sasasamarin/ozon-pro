#!/usr/bin/env bash
# Flowoi DB backup — pg_dump → gzip → /root/backups/auto/ с ротацией.
#
# Использование:
#   backup_db.sh              # label=auto (для systemd timer)
#   backup_db.sh manual       # ручной снимок с меткой
#   backup_db.sh pre-formulas # перед правками финформул
#
# Конфигурация: /etc/flowoi/backup.env (chmod 600, владелец root).
# Файл содержит DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME.
#
# Ротация: 14 дневных + 8 недельных + 6 месячных. Удаление снимков
# вне этих окон выполняется в конце каждого запуска.

set -euo pipefail

LABEL="${1:-auto}"
# label → безопасная строка для имени файла. printf без \n + чистим хвостовые _
SAFE_LABEL=$(printf '%s' "$LABEL" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_-' '_' | cut -c1-40 | sed -E 's/_+$//')

BACKUP_DIR="${BACKUP_DIR:-/root/backups/auto}"
ENV_FILE="${BACKUP_ENV:-/etc/flowoi/backup.env}"
TS=$(date -u +%Y%m%d_%H%M%S)
OUT="${BACKUP_DIR}/db_${SAFE_LABEL}_${TS}.sql.gz"

KEEP_DAILY=14    # 2 недели
KEEP_WEEKLY=8    # 2 месяца
KEEP_MONTHLY=6   # полгода

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

if [[ ! -r "$ENV_FILE" ]]; then
    log "ERROR: cannot read $ENV_FILE"
    exit 2
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${DB_HOST:?DB_HOST not set in $ENV_FILE}"
: "${DB_PORT:?DB_PORT not set in $ENV_FILE}"
: "${DB_USER:?DB_USER not set in $ENV_FILE}"
: "${DB_PASSWORD:?DB_PASSWORD not set in $ENV_FILE}"
: "${DB_NAME:?DB_NAME not set in $ENV_FILE}"
# Managed Selectel требует SSL — задаём через PGSSLMODE
DB_SSLMODE="${DB_SSLMODE:-require}"
export PGSSLMODE="$DB_SSLMODE"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

log "backup_start label=$SAFE_LABEL host=$DB_HOST db=$DB_NAME out=$OUT"

# pg_dump → gzip. PGPASSWORD только в env этого процесса, не в командной строке.
PGPASSWORD="$DB_PASSWORD" pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --no-owner \
    --no-acl \
    --format=plain \
    | gzip -9 > "$OUT.tmp"

# Атомарная замена — если pg_dump упал, .tmp остаётся, основной файл не появляется
mv "$OUT.tmp" "$OUT"
chmod 600 "$OUT"

SIZE_MB=$(du -m "$OUT" | cut -f1)
log "backup_done size_mb=$SIZE_MB file=$OUT"

# ─── Ротация ───
# Стратегия: всегда оставляем последние KEEP_DAILY снимков (любого label).
# Из остальных оставляем по 1 на уникальную ISO-неделю (KEEP_WEEKLY) и по 1 на месяц (KEEP_MONTHLY).
# Это сохраняет ручные снимки с особыми метками (pre-formulas, manual) в окне «недавних».

rotate() {
    # set -u + ассоц.массивы плохо дружат на пустом ключе, локально отключаем
    set +u
    local removed=0
    # Сортируем по mtime DESC
    mapfile -t FILES < <(find "$BACKUP_DIR" -maxdepth 1 -name 'db_*.sql.gz' -printf '%T@ %p\n' \
                          | sort -rn | awk '{print $2}')

    if [[ ${#FILES[@]} -eq 0 ]]; then
        set -u
        return
    fi

    declare -A seen_week=()
    declare -A seen_month=()
    declare -A keep=()

    local i=0
    for f in "${FILES[@]}"; do
        if (( i < KEEP_DAILY )); then
            keep[$f]=1
        fi
        i=$((i+1))

        local mt wk mo
        mt=$(stat -c %Y "$f")
        wk=$(date -u -d "@$mt" +%G-W%V)
        mo=$(date -u -d "@$mt" +%Y-%m)

        if [[ -z "${seen_week[$wk]+x}" && ${#seen_week[@]} -lt $KEEP_WEEKLY ]]; then
            seen_week[$wk]=1
            keep[$f]=1
        fi
        if [[ -z "${seen_month[$mo]+x}" && ${#seen_month[@]} -lt $KEEP_MONTHLY ]]; then
            seen_month[$mo]=1
            keep[$f]=1
        fi
    done

    for f in "${FILES[@]}"; do
        if [[ -z "${keep[$f]+x}" ]]; then
            rm -f "$f"
            removed=$((removed+1))
        fi
    done

    if (( removed > 0 )); then
        log "rotation_done removed=$removed kept=${#keep[@]}"
    fi
    set -u
}

rotate

log "backup_complete"
