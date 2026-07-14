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

```bash
mkdir -p nginx/ssl

# Установите certbot если нет
apt install certbot

# Получите сертификат (временно остановите nginx если запущен)
certbot certonly --standalone -d xtempls.ru -d www.xtempls.ru

# Скопируйте сертификаты
cp /etc/letsencrypt/live/xtempls.ru/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/xtempls.ru/privkey.pem nginx/ssl/
```

> **Для теста без домена** — уберите SSL-блок из `nginx/nginx.conf` и слушайте на 80.

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

```bash
certbot renew
cp /etc/letsencrypt/live/xtempls.ru/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/xtempls.ru/privkey.pem nginx/ssl/
docker compose restart nginx
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
