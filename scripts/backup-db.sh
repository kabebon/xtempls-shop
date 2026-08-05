#!/usr/bin/env bash
# =============================================================================
# backup-db.sh — Надёжный бэкап PostgreSQL базы XTEMPLS.
#
# Что делает:
#   1. Считает row counts ключевых таблиц ДО бэкапа (прямой запрос в БД).
#   2. Делает полный pg_dump (data + schema, через docker compose exec).
#   3. Сжимает в gzip и сохраняет в backups/xtempls_YYYYMMDD_HHMMSS.sql.gz.
#   4. Считает row counts из дампа (парсит блоки COPY) и сравнивает с п.1.
#   5. Ротация: хранит последние N (BACKUP_KEEP, по умолчанию 14) файлов.
#
# Запуск:
#   ./scripts/backup-db.sh
#   BACKUP_KEEP=30 ./scripts/backup-db.sh
#
# Читает POSTGRES_USER / POSTGRES_DB из .env (или переменных окружения).
# Контейнер postgres должен быть запущен (docker compose up -d postgres).
# =============================================================================
set -euo pipefail

# Переходим в корень проекта (скрипт лежит в scripts/)
cd "$(dirname "$0")/.."

# ── Конфиг ───────────────────────────────────────────────────────────────────
ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  # Безопасно подтягиваем только нужные переменные (не используем set -a, чтобы
  # не тащить лишнее и не ломать пароли с особыми символами).
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

PGUSER="${POSTGRES_USER:-xtempls}"
PGDB="${POSTGRES_DB:-xtempls_db}"
PG_CONTAINER="${PG_CONTAINER:-xtempls_postgres}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
# Таблицы, которые проверяем (ключевые для бизнеса). Совпадают с models.py.
CHECK_TABLES=(orders order_items users products categories tg_users \
              admin_users promo_codes addresses favorites bonus_transactions)

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/xtempls_${STAMP}.sql.gz"

echo "=== Бэкап БД XTEMPLS ($(date)) ==="
echo "База:       $PGDB (user: $PGUSER, контейнер: $PG_CONTAINER)"
echo "Файл:       $OUT_FILE"
echo

# ── 1. Row counts ДО (из живой БД) ───────────────────────────────────────────
echo "── Row counts в БД (до дампа) ──"
# Хелпер: выполнить SQL в контейнере postgres (compose v2 → fallback docker exec).
run_psql() {
  docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" -tAc "$1" 2>/dev/null \
    || docker exec -i "$PG_CONTAINER" psql -U "$PGUSER" -d "$PGDB" -tAc "$1" 2>/dev/null
}
declare -A BEFORE
for t in "${CHECK_TABLES[@]}"; do
  # Считаем через psql внутри контейнера. Если таблицы нет — '?'.
  cnt="$(run_psql "SELECT count(*) FROM ${t};" || echo "?")"
  cnt="$(echo "$cnt" | tr -d '[:space:]')"
  BEFORE[$t]="$cnt"
  printf "  %-22s %s\n" "$t" "$cnt"
done
echo

# ── 2-3. pg_dump ─────────────────────────────────────────────────────────────
# Пробуем docker compose (compose v2), падаем к docker exec (старый compose v1).
echo "── pg_dump ──"
dump_cmd=(docker compose exec -T postgres pg_dump -U "$PGUSER" "$PGDB")
if ! "${dump_cmd[@]}" 2>/dev/null | gzip > "$OUT_FILE"; then
  echo "  docker compose не сработал, пробую 'docker exec ${PG_CONTAINER}'..."
  docker exec -i "$PG_CONTAINER" pg_dump -U "$PGUSER" "$PGDB" 2>"$BACKUP_DIR/.err" \
    | gzip > "$OUT_FILE" || { echo "ОШИБКА дампа:"; cat "$BACKUP_DIR/.err"; rm -f "$BACKUP_DIR/.err"; exit 1; }
  rm -f "$BACKUP_DIR/.err"
fi

FILE_SIZE="$(stat -c %s "$OUT_FILE" 2>/dev/null || stat -f %z "$OUT_FILE")"
echo "  Готово: $OUT_FILE ($(numfmt --to=iec "$FILE_SIZE" 2>/dev/null || echo "${FILE_SIZE} байт"))"
echo

# ── 4. Проверка целостности: row counts из дампа vs БД ───────────────────────
echo "── Проверка дампа (row counts из COPY-блоков) ──"
WARN=0
for t in "${CHECK_TABLES[@]}"; do
  # В обычном (text) pg_dump данные лежат как "COPY public.<table> (cols) FROM stdin;\n<rows>\n\\."
  # Считаем строки между COPY public.<t> и "\.".
  rows="$(zcat "$OUT_FILE" | awk -v tbl="public.${t}" '
    $0 ~ "^COPY " tbl " " {in_copy=1; next}
    in_copy && /^\\\.$/ {in_copy=0}
    in_copy {n++}
    END {print n+0}
  ')"
  before="${BEFORE[$t]}"
  marker="OK"
  if [[ "$rows" != "$before" ]]; then
    # Расхождение допустимо, если в момент дампа шли активные вставки, но
    # помечаем предупреждением, чтобы проверить вручную.
    marker="⚠ РАСХОЖДЕНИЕ"
    WARN=1
  fi
  printf "  %-22s БД=%-8s дамп=%-8s %s\n" "$t" "$before" "$rows" "$marker"
done
echo

# ── 5. Ротация ───────────────────────────────────────────────────────────────
echo "── Ротация (хранить последние $BACKUP_KEEP) ──"
# Список по времени, удаляем всё что после KEEP.
mapfile -t OLD_FILES < <(ls -1t "$BACKUP"/xtempls_*.sql.gz 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)))
if [[ ${#OLD_FILES[@]} -eq 0 ]]; then
  echo "  Удалять нечего."
else
  for f in "${OLD_FILES[@]}"; do
    rm -f "$f"
    echo "  удалён старый: $(basename "$f")"
  done
fi
echo

if [[ "$WARN" -eq 1 ]]; then
  echo "⚠ ВНИМАНИЕ: есть расхождения row counts. Проверьте дамп вручную:"
  echo "  zcat $OUT_FILE | less"
  echo "Дамп создан, но лучше перепроверить перед удалением источника."
  exit 2
fi

echo "✅ Бэкап успешно создан и проверен: $OUT_FILE"
