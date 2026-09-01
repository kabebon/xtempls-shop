#!/usr/bin/env bash
# =============================================================================
# restore-db.sh — Восстановление PostgreSQL базы XTEMPLS из дампа.
#
# Использование:
#   ./scripts/restore-db.sh backups/xtempls_20260805_120000.sql.gz
#   ./scripts/restore-db.sh backups/xtempls_20260805_120000.sql.gz --fresh
#
# Поведение:
#   1. Считает row counts в целевой БД ДО восстановления.
#   2. Заливает дамп через psql (распаковывая .gz при необходимости).
#      По умолчанию данные ДОБАВЛЯЮТСЯ к существующим (это небезопасно при
#      конфликтах ID). Флаг --fresh сначала очищает схему (DROP+CREATE через
#      drop_schema), чтобы восстановление было чистым — ТОЛЬКО для пустой/новой
#      БД или когда вы готовы потерять текущие данные.
#   3. Считает row counts ПОСЛЕ и показывает разницу.
#
# ⚠ ВНИМАНИЕ: восстановление затирает/меняет данные. Делайте бэкап текущего
#   состояния перед restore. Скрипт просит подтверждение (или --yes чтобы skip).
# =============================================================================
set -euo pipefail

# Переходим в корень проекта
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a; . "$ENV_FILE"; set +a
fi

PGUSER="${POSTGRES_USER:-xtempls}"
PGDB="${POSTGRES_DB:-xtempls_db}"
PG_CONTAINER="${PG_CONTAINER:-xtempls_postgres}"
CHECK_TABLES=(orders order_items users products categories tg_users \
              admin_users promo_codes addresses favorites bonus_transactions)

DUMP_FILE="${1:-}"
if [[ -z "$DUMP_FILE" ]]; then
  echo "Использование: $0 <файл_дампа.sql[.gz]> [--fresh] [--yes]"
  echo "  --fresh  пересоздать схему перед заливкой (потеря текущих данных!)"
  echo "  --yes    без подтверждения"
  exit 1
fi
shift || true
FRESH=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --fresh) FRESH=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
  esac
done

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "ОШИБКА: файл дампа не найден: $DUMP_FILE"
  exit 1
fi

# Хелпер psql
run_psql() {
  docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" "$@" 2>/dev/null \
    || docker exec -i "$PG_CONTAINER" psql -U "$PGUSER" -d "$PGDB" "$@" 2>/dev/null
}

count_all() {
  echo "── Row counts в БД ($1) ──"
  for t in "${CHECK_TABLES[@]}"; do
    cnt="$(run_psql -tAc "SELECT count(*) FROM ${t};" 2>/dev/null || echo "?")"
    cnt="$(echo "$cnt" | tr -d '[:space:]')"
    printf "  %-22s %s\n" "$t" "$cnt"
    eval "${1^^}_$t=\"$cnt\""
  done
  echo
}

echo "=== Восстановление БД XTEMPLS из дампа ==="
echo "Дамп:  $DUMP_FILE"
echo "База:  $PGDB (контейнер postgres)"
[[ "$FRESH" -eq 1 ]] && echo "Режим: --fresh (схема будет пересоздана, текущие данные потеряны!)"
echo

# Подтверждение
if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -rp "Продолжить? Это изменит данные в БД «$PGDB». [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Отменено."; exit 0; }
fi

# 1. Counts до
count_all "before"

# 2. (Опц.) Очистка схемы
if [[ "$FRESH" -eq 1 ]]; then
  echo "── Очистка схемы (drop + recreate) ──"
  run_psql -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${PGUSER}; GRANT ALL ON SCHEMA public TO public;" -v ON_ERROR_STOP=1
  echo
fi

# 3. Заливка дампа
echo "── Заливка дампа ──"
# Определяем, gz или нет, и пускаем через пайп в psql.
case "$DUMP_FILE" in
  *.gz)
    zcat "$DUMP_FILE" | docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 2>/dev/null \
      || zcat "$DUMP_FILE" | docker exec -i "$PG_CONTAINER" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1
    ;;
  *.sql)
    docker compose exec -T postgres psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 < "$DUMP_FILE" 2>/dev/null \
      || docker exec -i "$PG_CONTAINER" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 < "$DUMP_FILE"
    ;;
  *)
    echo "ОШИБКА: неизвестный формат дампа (ожидается .sql или .sql.gz)"
    exit 1
    ;;
esac
echo "  Заливка завершена."
echo

# 4. Counts после
count_all "after"

echo "=== Восстановление завершено ==="
echo "Сравните counts до/после выше. Для пропущенных/ошибочных таблиц проверьте лог psql."
echo "Совет: после restore на новом сервере прогоните миграции: docker compose exec backend alembic upgrade head"
