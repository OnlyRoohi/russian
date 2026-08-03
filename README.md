# 💕 Couple Bot — Virtual GF/BF

A full dating-feel Telegram bot with **Russian 🇷🇺** and **Myanmar 🇲🇲** language support.  
Powered by **OpenAI GPT-4o-mini** with conversation memory. Users pay once with **Telegram Stars** to unlock unlimited chat.

---

## ✨ Features

| Feature | Details |
|---|---|
| 💑 Couple feel | Real GF/BF persona, uses your name, remembers chats |
| 🗣 Languages | Russian 🇷🇺 & Myanmar 🇲🇲 — switchable any time |
| 🧠 Memory | Last 20 messages kept for context (feels natural) |
| ⭐️ Payment | Telegram Stars — one-time, no Stripe/card needed |
| 👤 Profile | See your name, message count, join date |
| ✏️ Change name | Update what the bot calls you |
| 🗑 Clear history | Reset conversation any time |

---

## 🤖 Bot Flow

```
/start
  └─ Choose language (🇷🇺 / 🇲🇲)
       └─ Pay 100 ⭐️ (one-time)
            └─ "What's your name?"
                 └─ 💬 Start chatting as a couple!
```

---

## 📋 Commands

| Command | Action |
|---|---|
| `/start` | Start / restart bot |
| `/profile` | View your profile |
| `/lang` | Change language |
| `/reset` | Clear chat history |

**Menu Buttons** (keyboard):
- 💬 Chat
- 👤 My Profile
- ✏️ Change Name
- 🌐 Language
- 🗑 Clear History

---

## 🔧 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | BotFather token |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `STARS_PRICE` | ❌ | Stars cost (default: `100`) |
| `DB_PATH` | ❌ | SQLite path (default: `users.db`) |

---

## 🖥 Local Test

```bash
pip install -r requirements.txt
export BOT_TOKEN="your_bot_token"
export OPENAI_API_KEY="your_openai_key"
python bot.py
```

---

## 🚀 Heroku Deploy

```bash
# 1. Create Heroku app
heroku create your-app-name

# 2. Set environment variables
heroku config:set BOT_TOKEN="your_bot_token"
heroku config:set OPENAI_API_KEY="your_openai_key"
heroku config:set STARS_PRICE="100"

# 3. Push code
git init
git add .
git commit -m "couple bot"
heroku git:remote -a your-app-name
git push heroku main

# 4. Start worker dyno
heroku ps:scale worker=1
```

> ⚠️ **Heroku filesystem resets on restart** — `users.db` (paid users, names) will be lost.  
> For production, use **Heroku Postgres**:
> ```bash
> heroku addons:create heroku-postgresql:mini
> ```

---

## 💳 Telegram Stars Payment

- `provider_token` = `""` (empty string) — Stars need no payment provider
- `currency` = `"XTR"` — Telegram Stars currency code  
- Price = direct star count (100 = 100 Stars, no decimals)
- Automatically enabled on new bots via BotFather

---

## 🤖 BotFather Commands (set these)

```
start - Start the bot
profile - View your profile
lang - Change language
reset - Clear chat history
```
