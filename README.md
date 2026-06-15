# LINGVA.AI — AI-репетитор английского

Telegram-бот для изучения английского на **бесплатных API**.

## Стоимость — честная таблица (июнь 2026)

| Сервис | Бесплатно? | Лимиты free tier | Карта |
|--------|-----------|------------------|-------|
| **Gemini 2.5 Flash-Lite** | ✅ Да | ~30 RPM, ~1500 RPD, 1M TPM | Не нужна |
| **Groq LLM** (fallback) | ✅ Да | 30 RPM, 14400 RPD (8B) | Не нужна |
| **Groq Whisper** | ✅ Да | 20 RPM, 2000 RPD | Не нужна |
| **Edge TTS** | ✅ Да | Без лимитов API | — |
| **Datamuse** | ✅ Да | Щедрые лимиты | — |
| **RSS-новости** | ✅ Да | Без ключа | — |
| **Railway** | ⚠️ Trial | $5/мес trial, потом pay-as-you-go | Нужна для prod |

### ⚠️ Важно про Gemini

- **`gemini-2.0-flash` отключена с 01.06.2026** — не используйте!
- Бесплатный тир: только **Flash** и **Flash-Lite** модели
- **Pro-модели** с апреля 2026 — только с billing
- На free tier Google **может использовать промпты для обучения**
- Лимиты смотрите в [AI Studio → Rate limits](https://aistudio.google.com)

Официальные источники:
- [Gemini Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Groq Rate Limits](https://console.groq.com/docs/rate-limits)

## Быстрый старт (локально)

```bash
pip install -r requirements.txt
cp .env.example .env
# Заполните TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, GROQ_API_KEY
python scripts/check_apis.py   # проверка ключей
python bot.py                   # polling (без WEBHOOK_URL)
```

## Деплой на Railway

### 1. Подготовка

```bash
# Установите Railway CLI: https://docs.railway.com/develop/cli
npm i -g @railway/cli
railway login
```

### 2. Создание проекта

```bash
cd lingvatrainer_bot
railway init          # создать новый проект
railway link          # или привязать к существующему
```

### 3. Переменные окружения

В Railway Dashboard → **Variables** (или CLI):

```
TELEGRAM_BOT_TOKEN=...
GEMINI_API_KEY=...
GROQ_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash-lite
GROQ_LLM_MODEL=llama-3.1-8b-instant
DB_PATH=/data/lingva.db
```

`RAILWAY_PUBLIC_DOMAIN` и `PORT` Railway выставит автоматически → webhook включится сам.

### 4. Volume для SQLite (обязательно!)

Без volume база **сбрасывается при каждом redeploy**.

1. Railway Dashboard → ваш сервис → **Volumes**
2. Add Volume: mount path **`/data`**, size 1 GB
3. `DB_PATH=/data/lingva.db` уже в Dockerfile

### 5. Деплой

```bash
railway up
```

Или подключите GitHub repo — Railway соберёт из `Dockerfile` + `railway.toml`.

### 6. Проверка

```bash
curl https://YOUR-APP.up.railway.app/health
# → OK
```

Логи: `railway logs`

### Troubleshooting: Healthcheck failure

| Причина | Решение |
|---------|---------|
| **Старый код на Railway** | В логах должно быть `LINGVA.AI v1.1.0-railway` и `Boot mode=webhook`. Если `Starting polling...` — передеплойте! |
| Нет `TELEGRAM_BOT_TOKEN` | Variables → ключ от @BotFather |
| `DB_PATH=/data/...` без volume | **Удалите** `DB_PATH` из Variables или поставьте `/app/data/lingva.db` |
| Нет Public Domain | Settings → Networking → **Generate Domain** |

**В Railway Variables удалите или исправьте:**
```
DB_PATH=/data/lingva.db   ← УДАЛИТЬ (ломает без volume)
```

После деплоя в логах:
```
LINGVA.AI entrypoint
Boot mode=webhook v1.1.0-railway
HTTP server on 0.0.0.0:8080
БД инициализирована.
```

## Архитектура

```
bot.py              # Webhook (Railway) / Polling (local)
config.py           # Env-настройки
database.py         # SQLite + миграции
scheduler.py        # Напоминания SRS

handlers/           # Telegram-роутеры
api/                # Gemini → Groq fallback, Whisper, Datamuse, RSS
services/           # Сессии, XP, streak
utils/              # Edge TTS, текст
```

## Проверка API перед деплоем

```bash
python scripts/check_apis.py
```

Проверяет: Telegram bot, Gemini model, Groq LLM.
