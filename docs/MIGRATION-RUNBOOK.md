# Runbook: миграция / переезд базы XTEMPLS

Чек-лист, чтобы при переносе базы (на новый сервер, в новый контейнер) **не
потерялись данные** — особенно история заказов. Составлен после инцидента,
когда при переезде заказы у людей пропали из личного кабинета.

> TL;DR: дамп = `scripts/backup-db.sh`, заливка = `scripts/restore-db.sh`.
> Главное правило — **сравнивать row counts каждой таблицы до и после**.

---

## 0. Почему вообще теряются данные

Типичные причины (по убыванию частоты):

1. **Сделали `pg_dump --schema-only`** (только структура, без данных) или
   выгрузили через Alembic-миграции (Alembic переносит схему, **не данные**).
   В итоге таблицы есть, а строки — пустые.
2. **Залили дамп в БД с уже существующими данными** и поймали конфликты
   primary key → psql тихо пропустил часть строк (без `ON_ERROR_STOP`).
3. **Забыли таблицу** в дампе (например `order_items` или `bonus_transactions`).
4. **Старый дамп** — восстановили то, что было на вчера, а не «прямо сейчас».

Скрипты в `scripts/` закрывают все 4 случая: полный `pg_dump` (data+schema),
`ON_ERROR_STOP`, проверка row counts по 12 ключевым таблицам.

---

## 1. Что переносим (полный список таблиц)

Все таблицы из `backend/models.py`. Никаких «можно пропустить»:

| Таблица | Модель | Почему важно |
|---|---|---|
| `orders` | `Order` | **История заказов** — то, что терялось |
| `order_items` | `OrderItem` | Состав заказов (позиции) |
| `users` | `User` | Аккаунты личного кабинета |
| `addresses` | `Address` | Адреса доставки |
| `favorites` | `Favorite` | Избранное |
| `bonus_transactions` | `BonusTransaction` | История бонусов |
| `tg_users` | `TgUser` | Подписчики бота |
| `products` | `Product` | Каталог |
| `product_images` | `ProductImage` | Картинки товаров |
| `product_sizes` | `ProductSize` | Размеры/склад |
| `categories` | `Category` | Категории |
| `admin_users` | `AdminUser` | Учётки админов |
| `promo_codes` | `PromoCode` | Промокоды |

Полный `pg_dump` (без `--schema-only` / без `--table`) захватывает **все**
таблицы автоматически. Дополнительно — том `uploads_data` с картинками
товаров (файлы, не в БД): его копируем отдельно (см. §5).

---

## 2. Перед переездом — снять эталонные counts

На **старом** сервере, пока он ещё жив, снимаем row counts каждой таблицы.
Это база для сравнения после заливки.

```bash
# На старом сервере, в корне проекта:
./scripts/backup-db.sh
# Скрипт сам выведет row counts всех таблиц — сохраните этот вывод!

# Или вручную, если скрипта ещё нет:
docker compose exec postgres psql -U xtempls -d xtempls_db -c "
SELECT 'orders' AS t, count(*) FROM orders
UNION ALL SELECT 'order_items', count(*) FROM order_items
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'tg_users', count(*) FROM tg_users
UNION ALL SELECT 'addresses', count(*) FROM addresses
UNION ALL SELECT 'favorites', count(*) FROM favorites
UNION ALL SELECT 'bonus_transactions', count(*) FROM bonus_transactions;
"
```

**Сохраните вывод в файл** — это ваш чек. Без него проверить «всё ли
перенеслось» будет невозможно.

---

## 3. Бэкап (старый сервер)

```bash
./scripts/backup-db.sh
# → backups/xtempls_YYYYMMDD_HHMMSS.sql.gz
```

Скрипт:
- делает полный `pg_dump` (схема + данные всех таблиц);
- считает row counts из дампа (парсит блоки `COPY`) и сравнивает с живой БД;
- ругается (`exit 2`) при расхождениях;
- хранит последние 14 дампов (`BACKUP_KEEP=14`).

Если скрипта нет — ручная команда (полный дамп!):

```bash
docker compose exec -T postgres pg_dump -U xtempls xtempls_db | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

Перенесите `.sql.gz` на новый сервер (`scp`, `rsync`).

---

## 4. Восстановление (новый сервер)

### 4a. Чистая новая БД (рекомендуется)

```bash
# Контейнеры подняты, база пустая (миграции ещё не гонялись, или гонялись и пустые):
./scripts/restore-db.sh backups/xtempls_YYYYMMDD_HHMMSS.sql.gz --fresh --yes
```

`--fresh` пересоздаёт схему `public` перед заливкой → дамп привносит свою
схему (из `CREATE TABLE`) + данные. Чисто, без конфликтов ID.

### 4b. Поверх существующей БД (осторожно)

```bash
./scripts/restore-db.sh backups/xtempls_YYYYMMDD_HHMMSS.sql.gz
```

Без `--fresh` данные **добавляются** к текущим. Если ID пересекаются — будут
ошибки дубликатов (psql с `ON_ERROR_STOP=1` остановится). Используйте только
если точно понимаете, что делаете.

### 4c. После заливки — прогнать миграции

Дамп несёт схему того момента, когда был снят. Если между этим и кодом на
новом сервере есть расхождения (новые колонки) — Alembic доведёт до актуала:

```bash
docker compose exec backend alembic upgrade head
```

Alembic **идемпотентен**: применит только недостающие миграции.

---

## 5. Файлы (не в БД)

Картинки товаров живут в Docker volume `uploads_data`, **не в БД**. Их тоже
надо переносить:

```bash
# На старом сервере — выгрузить том:
docker run --rm -v xtempls_uploads_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/uploads_data.tar.gz -C /data .

# На новом — загрузить:
docker run --rm -v xtempls_uploads_data:/data -v "$PWD":/backup alpine \
  tar xzf /backup/uploads_data.tar.gz -C /data
```

Проверьте, что volume называется именно `xtempls_uploads_data` (имя из
`docker-compose.yml` + имя проекта).

---

## 6. Сверка после переезда

**Главный шаг.** Сравнить counts с эталоном из §2:

```bash
# На новом сервере:
./scripts/backup-db.sh    # или restore-db.sh уже вывел after-counts
# Сравните с эталоном из §2 — цифры должны совпадать.
```

Дополнительно — точечная проверка через личный кабинет:
- зайдите под аккаунтом реального покупателя;
- проверьте, что история заказов на месте и счётчик «заказов» корректный.

Если counts совпадают — переезд успешен. Если нет — не удаляйте старый сервер,
разбирайтесь с конкретной таблицей.

---

## 7. Автоматические бэкапы (cron)

Чтобы не ловить потерю постфактум, бэкап должен быть регулярным. На сервере
(хосте, где работает `docker compose`):

```bash
# Откройте crontab пользователя, от которого запускается compose:
crontab -e

# Ежедневно в 03:00 — полный бэкап с ротацией:
0 3 * * * cd /path/to/xtmepls_bot && ./scripts/backup-db.sh >> logs/backup.log 2>&1
```

Проверьте, что `logs/` существует и `docker compose` доступен в PATH cron
(часто нужен полный путь: `/usr/local/bin/docker`).

Альтернатива — cron-контейнер в compose, но это усложняет стек; системный
cron проще и достаточно надёжен.

---

## 8. Восстановление потерянных заказов (из старого дампа)

Если история уже пропала, но **старый дамп/сервер доступны**:

1. Найдите дамп, где заказы ещё есть (по дате — до переезда).
2. Снимите counts из него:
   ```bash
   zcat backups/old_dump.sql.gz | grep -c "^COPY public.orders "
   zcat backups/old_dump.sql.gz | awk '/^COPY public.orders /{c=1;next} /^\\\.$/{c=0} c{print}' | wc -l
   ```
3. На целевом сервере **не трогайте** текущие `orders` напрямую (риск
   повредить). Лучше:
   - разверните старый дамп в **временную** БД (`xtempls_restore`);
   - скопируйте недостающие строки SQL-запросом с проверкой конфликтов ID:

   ```sql
   -- В БД-приёмнике, из временной БД (через dblink или вручную):
   INSERT INTO orders (id, tg_user_chat_id, user_id, customer_name, customer_phone,
     customer_telegram, delivery_address, comment, status, order_type,
     payment_status, payment_label, amount, created_at, updated_at, is_deleted)
   SELECT id, tg_user_chat_id, user_id, customer_name, customer_phone,
     customer_telegram, delivery_address, comment, status, order_type,
     payment_status, payment_label, amount, created_at, updated_at, is_deleted
   FROM source_db.orders
   ON CONFLICT (id) DO NOTHING;   -- пропускаем уже существующие
   ```
   Аналогично — для `order_items` (по `order_id` + `id`).

4. Если **старого дампа нет** — восстановить невозможно. Это подчёркивает,
   почему регулярный бэкап (§7) критичен.

---

## 9. Шпаргалка

```bash
# Бэкап (с проверкой):
./scripts/backup-db.sh

# Восстановление в чистую БД:
./scripts/restore-db.sh backups/xtempls_YYYYMMDD_HHMMSS.sql.gz --fresh

# Снять counts вручную:
docker compose exec postgres psql -U xtempls -d xtempls_db -c "SELECT count(*) FROM orders;"

# Прогнать миграции после restore:
docker compose exec backend alembic upgrade head
```
