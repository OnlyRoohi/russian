# Твоя тянка / သင့်ချစ်သူ — Telegram Bot

A virtual girlfriend Telegram bot with **Russian 🇷🇺** and **Myanmar 🇲🇲** language support, powered by OpenAI GPT-4o-mini. Users pay once with Telegram Stars to unlock unlimited AI chat.

---

## Features
- `/start` — welcome message + payment button
- `/lang` — switch language (Russian ↔ Myanmar)
- Telegram Stars payment (100 ⭐️ one-time, configurable)
- OpenAI GPT-4o-mini powered responses
- SQLite database for paid users + language preferences

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | BotFather token |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `STARS_PRICE` | ❌ | Stars cost (default: `100`) |
| `DB_PATH` | ❌ | SQLite file path (default: `users.db`) |

---

## Local Test

```bash
pip install -r requirements.txt
export BOT_TOKEN="your_bot_token"
export OPENAI_API_KEY="your_openai_key"
python bot.py
```

---

## Heroku Deploy

### Step 1 — Create app
```bash
heroku create your-app-name
```

### Step 2 — Set environment variables
```bash
heroku config:set BOT_TOKEN="your_bot_token"
heroku config:set OPENAI_API_KEY="your_openai_key"
heroku config:set STARS_PRICE="100"
```

### Step 3 — Push code
```bash
git init
git add .
git commit -m "init"
heroku git:remote -a your-app-name
git push heroku main
```

### Step 4 — Start worker dyno
```bash
heroku ps:scale worker=1
```

> ⚠️ **Important:** Use `worker` dyno (not `web`). This is already set in the `Procfile`.
>
> 🔴 **Heroku filesystem is ephemeral** — `users.db` resets on dyno restart. For production, add Heroku Postgres:
> ```bash
> heroku addons:create heroku-postgresql:mini
> ```
> Then update `bot.py` to use `DATABASE_URL` with `psycopg2` instead of SQLite.

---

## How Telegram Stars Payment Works
- `provider_token` is empty string — Telegram Stars don't need a payment provider
- Currency is `"XTR"` (Telegram Stars)
- Price is direct star count (100 = 100 stars, no decimal math)
- Automatically enabled for new bots via BotFather

---

## Bot Commands (set in BotFather)
```
start - Start the bot
lang - Change language / ဘာသာစကား ပြောင်းရန်
```
