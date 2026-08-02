# XTEMPLS — Telegram Mini App Магазин одежды

Telegram-бот с Mini App для магазина одежды. Витрина товаров с каталогом, фильтрами и детальными страницами. Отдельная защищённая административная панель.

## Стек

| Компонент | Технология |
|---|---|
| Bot | Python 3.12 + aiogram 3 |
| API | FastAPI + SQLAlchemy 2 (async) |
| DB | PostgreSQL 16 |
| Frontend | Vanilla HTML/CSS/JS |
| Web Server | Nginx |
| Containers | Docker Compose |

## Структура

```
xtmepls_bot/
├── bot/          # Telegram бот
├── backend/      # FastAPI API
├── frontend/     # Mini App (каталог, страница товара)
├── admin/        # Админ панель
├── nginx/        # Nginx конфиг
└── docker-compose.yml
```

---

## Развёртывание на сервере

### 1. Клонирование

```bash
git clone <your-repo> xtmepls_bot
cd xtmepls_bot
```

### 2. Переменные окружения

```bash
cp .env.example .env
nano .env
```

Заполните:
- `TELEGRAM_BOT_TOKEN` — токен от @BotFather
- `POSTGRES_PASSWORD` — надёжный пароль БД
- `SECRET_KEY` — длинная случайная строка (минимум 32 символа)
- `ADMIN_DEFAULT_LOGIN` / `ADMIN_DEFAULT_PASSWORD` — данные первого админа

### 3. SSL-сертификат (Let's Encrypt)

HTTPS терминируется **внутри compose-nginx**. Сертификаты лежат на хосте в
`/etc/letsencrypt` и монтируются в контейнер через симлинк `./nginx/ssl`.
Порядок важен: сертификат надо выпустить **до** `docker compose up`, иначе
nginx не стартует (SSL-блок ссылается на ещё не существующие `.pem`).

```bash
# Установите certbot на хост
apt update && apt install -y certbot

# Свяжите каталог для монтирования (compose монтирует ./nginx/ssl)
ln -s /etc/letsencrypt ./nginx/ssl
mkdir -p ./nginx/acme   # webroot для продления

# Выпустите сертификат. ВАЖНО: A-запись домена уже должна указывать на этот
# сервер, а порт 80 должен быть свободен (compose ещё не запущен).
certbot certonly --standalone -d xtempls.ru -d www.xtempls.ru \
  --agree-tos -m you@example.com --no-eff-email

# Проверьте, что симлинк «работает» изнутри проекта:
ls ./nginx/ssl/live/xtempls.ru/fullchain.pem
```

**Автопродление** (certbot renew + рестарт nginx, чтобы подхватить новые `.pem`):

```bash
echo "0 3 * * * certbot renew --quiet --deploy-hook 'docker restart xtempls_nginx'" \
  | sudo tee /etc/cron.d/certbot-renew
```

> **Для теста без домена** — уберите SSL-блок (`listen 443 ssl`) из `nginx/nginx.conf`,
> оставьте только `listen 80`, и в `docker-compose.yml` закомментируйте mount `./nginx/ssl`.

### 4. Запуск

```bash
docker compose up -d --build
```

### 5. Проверка

```bash
# Логи всех сервисов
docker compose logs -f

# Проверить API
curl https://xtempls.ru/api/health

# Проверить бота
# Написать /start в Telegram
```

---

## Доступ к сервисам

| Сервис | URL |
|---|---|
| Mini App (каталог) | `https://xtempls.ru/` |
| Админка (вход) | `https://xtempls.ru/admin/` |
| Дашборд | `https://xtempls.ru/admin/dashboard.html` |
| Товары | `https://xtempls.ru/admin/products.html` |
| Категории | `https://xtempls.ru/admin/categories.html` |
| API Docs | `https://xtempls.ru/api/docs` |

---

## Настройка в Telegram

### Зарегистрировать Mini App у BotFather

```
1. @BotFather → /newapp
2. Выберите своего бота
3. URL: https://xtempls.ru
4. Опционально: /setmenubutton — добавить кнопку меню
```

### Добавить кнопку меню

```
/setmenubutton → выбрать бота → Web App → https://xtempls.ru
```

---

## Управление

### Обновление

```bash
git pull
docker compose up -d --build backend bot
```

### Обновление SSL-сертификата

Происходит автоматически через cron (см. раздел «SSL» выше — `certbot renew` +
`--deploy-hook 'docker restart xtempls_nginx'`). Копировать `.pem` вручную **не
нужно**: контейнер читает сертификаты прямо из примонтированного `/etc/letsencrypt`.

Ручная проверка продления:

```bash
certbot renew --dry-run
```

### Просмотр логов

```bash
docker compose logs backend -f   # API логи
docker compose logs bot -f       # Bot логи
docker compose logs nginx -f     # Nginx логи
```

### Бэкап БД

```bash
docker compose exec postgres pg_dump -U xtempls xtempls_db > backup_$(date +%Y%m%d).sql
```

### Восстановление БД

```bash
cat backup.sql | docker compose exec -T postgres psql -U xtempls -d xtempls_db
```

---

## Добавление второго администратора

Через API (с токеном главного админа):
```bash
# Пока нет эндпоинта — добавьте через psql:
docker compose exec postgres psql -U xtempls -d xtempls_db

# В psql:
INSERT INTO admin_users (login, password_hash, is_active)
VALUES ('newadmin', '<bcrypt_hash>', true);
```

Или добавьте эндпоинт `POST /api/admin/users` при необходимости.

---

## API документация

FastAPI автоматически генерирует документацию:
- **Swagger UI**: `https://xtempls.ru/api/docs`
- **ReDoc**: `https://xtempls.ru/api/redoc`

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `WEBAPP_URL` | URL Mini App (`https://xtempls.ru`) |
| `POSTGRES_USER` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `POSTGRES_DB` | Имя базы данных |
| `DATABASE_URL` | Полный URL подключения к БД |
| `SECRET_KEY` | Секрет для JWT (мин. 32 символа) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Время жизни JWT (дефолт: 1440 = 24ч) |
| `ADMIN_DEFAULT_LOGIN` | Логин первого администратора |
| `ADMIN_DEFAULT_PASSWORD` | Пароль первого администратора |
| `ALLOWED_ORIGINS` | CORS origins (через запятую) |
