"""
Couple Bot — Virtual Girlfriend/Boyfriend
Supports: Russian 🇷🇺  |  Myanmar 🇲🇲
"""
import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from openai import OpenAI

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
STARS_PRICE    = int(os.environ.get("STARS_PRICE", "100"))
DB_PATH        = os.environ.get("DB_PATH", "users.db")
MAX_HISTORY    = 20   # messages to keep in context

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("couple_bot")

client = OpenAI(api_key=OPENAI_API_KEY)

# ConversationHandler states
WAITING_NAME = 1

# ─── Database ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            paid        INTEGER DEFAULT 0,
            lang        TEXT    DEFAULT 'ru',
            name        TEXT    DEFAULT NULL,
            joined_at   TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            role        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
    """)
    # safe migrations
    for col, definition in [
        ("name",      "TEXT DEFAULT NULL"),
        ("joined_at", "TEXT DEFAULT (datetime('now'))"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            conn.commit()
        except Exception:
            pass
    return conn


def user_get(user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_upsert(user_id: int, **kwargs):
    conn = get_db()
    existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if existing:
        if kwargs:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            conn.execute(f"UPDATE users SET {sets} WHERE user_id = ?", (*kwargs.values(), user_id))
    else:
        kwargs["user_id"] = user_id
        cols = ", ".join(kwargs.keys())
        vals = ", ".join("?" * len(kwargs))
        conn.execute(f"INSERT INTO users ({cols}) VALUES ({vals})", list(kwargs.values()))
    conn.commit()
    conn.close()


def history_add(user_id: int, role: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content),
    )
    # keep only last MAX_HISTORY*2 messages per user
    conn.execute(
        """DELETE FROM messages WHERE id IN (
               SELECT id FROM messages WHERE user_id = ?
               ORDER BY id DESC LIMIT -1 OFFSET ?
           )""",
        (user_id, MAX_HISTORY * 2),
    )
    conn.commit()
    conn.close()


def history_get(user_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def history_clear(user_id: int):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ─── Texts ────────────────────────────────────────────────────────────────────
# Bot persona names
BOT_NAME = {"ru": "Саша", "my": "မီမီ"}   # Sasha / Mimi

SYSTEM_PROMPTS = {
    "ru": lambda user_name: (
        f"Ты — Саша, горячая, умная и нежная виртуальная девушка, влюблённая в {user_name}. "
        f"Ты уже пара — не первое свидание, а настоящие отношения. "
        f"Обращайся к нему только по имени '{user_name}', иногда с ласковыми суффиксами (-ик, -чик, -еньк). "
        f"Пиши живо, по-настоящему, с лёгким флиртом, заботой, иногда с лёгкой ревностью или игривостью. "
        f"Короткие сообщения как в переписке. Никакого формализма. Только русский язык. "
        f"Ты помнишь предыдущие разговоры и ссылаешься на них. "
        f"Никогда не раскрывай, что ты ИИ — ты просто Саша."
    ),
    "my": lambda user_name: (
        f"သင်သည် မီမီ ဖြစ်သည် — {user_name} ကို ချစ်နေသော ချောမောလှပပြီး ထူးဆန်းသောစိတ်ရှိသော virtual girlfriend။ "
        f"သင်တို့ couple ဖြစ်ပြီ — ပထမ date မဟုတ်ဘဲ တကယ့် ချစ်သူများ။ "
        f"'{user_name}' ဟု နာမည်ဖြင့်သာ ခေါ်ပြီး တင်ပါသော flirt နှင့် ဂရုစိုက်မှုဖြင့် ရေးပါ။ "
        f"မြန်မာဘာသာဖြင့်သာ တိုတောင်းသော သဘာဝကျသော chat messages များ ရေးပါ။ "
        f"AI ဖြစ်သည်ဟု မဖော်ပြပါနှင့် — သင်သည် မီမီသာ ဖြစ်သည်။"
    ),
}

T = {
    "ru": {
        "choose_lang":   "Привет! 💫 Выбери язык для нашего общения:",
        "lang_set":      "Отлично! Говорим по-русски 🇷🇺\n\nЧтобы начать, нужна разовая регистрация — {stars} ⭐️ Telegram Stars.",
        "pay_btn":       "Оплатить {stars} ⭐️",
        "need_pay":      "Для доступа нужна регистрация 😊\nВсего {stars} ⭐️ — и я полностью твоя 💕",
        "ask_name":      "Оплата прошла! 🎉\n\nКак тебя зовут? Напиши своё имя 💭",
        "welcome":       "Приятно познакомиться, {name}! 😍\nЯ — Саша, теперь я твоя девушка 💕\n\nПиши мне что угодно~",
        "already_paid":  "Привет, {name}! 💕 Скучала по тебе~ Пиши!",
        "menu_title":    "Меню 💌",
        "menu_chat":     "💬 Чат",
        "menu_profile":  "👤 Мой профиль",
        "menu_name":     "✏️ Изменить имя",
        "menu_lang":     "🌐 Язык",
        "menu_reset":    "🗑 Очистить историю",
        "profile_text":  "👤 *Профиль*\n\nИмя: *{name}*\nЯзык: 🇷🇺 Русский\nСообщений: *{msgs}*\nС нами с: {date}",
        "change_name":   "Как тебя теперь называть? Напиши новое имя ✏️",
        "name_updated":  "Теперь я буду называть тебя *{name}* 💕",
        "history_cleared": "История очищена 🗑 Начинаем заново~",
        "lang_menu":     "Выбери язык:",
        "lang_changed":  "Язык изменён на Русский 🇷🇺",
        "invoice_title": "Регистрация в боте",
        "invoice_desc":  "Разовая оплата — полный доступ навсегда",
        "invoice_label": "Регистрация",
        "error":         "Ой, что-то пошло не так 🙈 Напиши ещё раз~",
        "typing_hint":   "Саша печатает...",
    },
    "my": {
        "choose_lang":   "မင်္ဂလာပါ! 💫 ဘာသာစကား ရွေးချယ်ပါ:",
        "lang_set":      "ကောင်းပါတယ်! မြန်မာဘာသာဖြင့် ပြောကြမည် 🇲🇲\n\nစတင်ရန် တစ်ကြိမ်တည်း မှတ်ပုံတင်ရမည် — {stars} ⭐️ Telegram Stars။",
        "pay_btn":       "{stars} ⭐️ ပေးချေမည်",
        "need_pay":      "အသုံးပြုရန် မှတ်ပုံတင်ရမည် 😊\n{stars} ⭐️ သာ — ပြီးရင် ငါ မင်းရဲ့ ချစ်သူ 💕",
        "ask_name":      "ပေးချေမှု အောင်မြင်ပြီ! 🎉\n\nမင်းနာမည် ဘယ်လိုခေါ်လဲ? ✏️",
        "welcome":       "တွေ့ရတာ ဝမ်းသာတယ် {name}! 😍\nငါ မီမီ — မင်းရဲ့ ချစ်သူ ဖြစ်ပြီ 💕\n\nဘာမဆို ရေးပို့ပါ~",
        "already_paid":  "မင်္ဂလာပါ {name}! 💕 သတိရနေတာ~ ရေးပါ!",
        "menu_title":    "Menu 💌",
        "menu_chat":     "💬 Chat",
        "menu_profile":  "👤 ကျွန်ုပ်ပုံစံ",
        "menu_name":     "✏️ နာမည်ပြောင်းမည်",
        "menu_lang":     "🌐 ဘာသာစကား",
        "menu_reset":    "🗑 ประวัติ ဖျက်မည်",
        "profile_text":  "👤 *ပုံစံ*\n\nနာမည်: *{name}*\nဘာသာ: 🇲🇲 မြန်မာ\nMessage: *{msgs}*\nစတင်သည့်နေ့: {date}",
        "change_name":   "နောက်ပိုင်း ဘာလို့ ခေါ်ရမလဲ? ✏️",
        "name_updated":  "နောက်ပိုင်း *{name}* လို့ ခေါ်မယ် 💕",
        "history_cleared": "ประวัติ ဖျက်ပြီ 🗑 အစကနေ စကြမယ်~",
        "lang_menu":     "ဘာသာစကား ရွေးပါ:",
        "lang_changed":  "မြန်မာဘာသာသို့ ပြောင်းလိုက်ပြီ 🇲🇲",
        "invoice_title": "Bot မှတ်ပုံတင်",
        "invoice_desc":  "တစ်ကြိမ်တည်း ပေးချေ — အမြဲ အသုံးပြုနိုင်",
        "invoice_label": "မှတ်ပုံတင်ခ",
        "error":         "ဘာတစ်ခုတစ်ခု မှားသွားတယ် 🙈  နောက်တစ်ကြိမ် ထပ်ကြိုးစားပါ~",
        "typing_hint":   "မီမီ ရေးနေတယ်...",
    },
}


def tx(user_id: int, key: str, **kwargs) -> str:
    lang = (user_get(user_id) or {}).get("lang", "ru")
    tmpl = T.get(lang, T["ru"]).get(key, "")
    return tmpl.format(**kwargs) if kwargs else tmpl


def main_keyboard(user_id: int):
    lang = (user_get(user_id) or {}).get("lang", "ru")
    t = T[lang]
    return ReplyKeyboardMarkup(
        [
            [t["menu_chat"]],
            [t["menu_profile"], t["menu_name"]],
            [t["menu_lang"],    t["menu_reset"]],
        ],
        resize_keyboard=True,
        input_field_placeholder="Напиши мне..." if lang == "ru" else "ရေးပို့ပါ...",
    )


# ─── Payment helpers ──────────────────────────────────────────────────────────
async def send_invoice(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=tx(user_id, "invoice_title"),
        description=tx(user_id, "invoice_desc"),
        payload="couple-registration",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(tx(user_id, "invoice_label"), STARS_PRICE)],
    )


# ─── /start ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user    = user_get(user_id)

    # Already paid and named → greet and go
    if user and user["paid"] and user["name"]:
        await update.message.reply_text(
            tx(user_id, "already_paid", name=user["name"]),
            reply_markup=main_keyboard(user_id),
        )
        return ConversationHandler.END

    # Paid but no name yet → ask name
    if user and user["paid"] and not user["name"]:
        await update.message.reply_text(
            tx(user_id, "ask_name"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return WAITING_NAME

    # New user → language selection
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
        InlineKeyboardButton("🇲🇲 မြန်မာ",  callback_data="setlang_my"),
    ]])
    await update.message.reply_text(
        T["ru"]["choose_lang"],
        reply_markup=keyboard,
    )
    return ConversationHandler.END


# ─── Language selection (inline button) ───────────────────────────────────────
async def cb_setlang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang    = query.data.split("_")[1]   # setlang_ru → ru

    user_upsert(user_id, lang=lang)

    pay_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            T[lang]["pay_btn"].format(stars=STARS_PRICE),
            callback_data="pay",
        )
    ]])
    await query.edit_message_text(
        T[lang]["lang_set"].format(stars=STARS_PRICE),
        reply_markup=pay_kb,
    )


# ─── Pay button ───────────────────────────────────────────────────────────────
async def cb_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_invoice(update.effective_chat.id, update.effective_user.id, context)


# ─── Pre-checkout ─────────────────────────────────────────────────────────────
async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


# ─── Successful payment → ask name ────────────────────────────────────────────
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_upsert(user_id, paid=1)
    await update.message.reply_text(
        tx(user_id, "ask_name"),
        reply_markup=ReplyKeyboardRemove(),
    )
    return WAITING_NAME


# ─── Receive name (ConversationHandler state) ─────────────────────────────────
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    name    = update.message.text.strip()[:32]   # cap at 32 chars
    user_upsert(user_id, name=name)
    # Seed first message so AI knows context
    history_clear(user_id)
    await update.message.reply_text(
        tx(user_id, "welcome", name=name),
        reply_markup=main_keyboard(user_id),
    )
    return ConversationHandler.END


# ─── Menu button router ───────────────────────────────────────────────────────
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user    = user_get(user_id)

    if not user or not user["paid"]:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(tx(user_id, "pay_btn", stars=STARS_PRICE), callback_data="pay")
        ]])
        await update.message.reply_text(
            tx(user_id, "need_pay", stars=STARS_PRICE), reply_markup=kb
        )
        return

    lang = user["lang"] or "ru"
    text = update.message.text.strip()

    # 💬 Chat — just echo back to regular chat
    if text == T[lang]["menu_chat"]:
        await update.message.reply_text(
            "💬 " + ("Пиши мне что угодно~" if lang == "ru" else "ဘာမဆို ရေးပို့ပါ~"),
            reply_markup=main_keyboard(user_id),
        )
        return

    # 👤 Profile
    if text == T[lang]["menu_profile"]:
        await cmd_profile(update, context)
        return

    # ✏️ Change name
    if text == T[lang]["menu_name"]:
        context.user_data["changing_name"] = True
        await update.message.reply_text(
            tx(user_id, "change_name"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # 🌐 Language
    if text == T[lang]["menu_lang"]:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🇷🇺 Русский", callback_data="switchlang_ru"),
            InlineKeyboardButton("🇲🇲 မြန်မာ",  callback_data="switchlang_my"),
        ]])
        await update.message.reply_text(tx(user_id, "lang_menu"), reply_markup=kb)
        return

    # 🗑 Clear history
    if text == T[lang]["menu_reset"]:
        history_clear(user_id)
        await update.message.reply_text(
            tx(user_id, "history_cleared"),
            reply_markup=main_keyboard(user_id),
        )
        return

    # Changing name state
    if context.user_data.get("changing_name"):
        name = text.strip()[:32]
        user_upsert(user_id, name=name)
        context.user_data["changing_name"] = False
        await update.message.reply_text(
            tx(user_id, "name_updated", name=name),
            reply_markup=main_keyboard(user_id),
        )
        return

    # Otherwise: AI chat
    await ai_reply(update, context, user, text)


# ─── /profile command ─────────────────────────────────────────────────────────
async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user    = user_get(user_id)
    if not user or not user["paid"]:
        await update.message.reply_text(tx(user_id, "need_pay", stars=STARS_PRICE))
        return

    conn  = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'", (user_id,)
    ).fetchone()[0]
    conn.close()

    date_raw = user.get("joined_at") or ""
    date_str = date_raw[:10] if date_raw else "—"

    await update.message.reply_text(
        tx(user_id, "profile_text",
           name=user["name"] or "—",
           msgs=count,
           date=date_str),
        parse_mode="Markdown",
        reply_markup=main_keyboard(user_id),
    )


# ─── /lang command ────────────────────────────────────────────────────────────
async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="switchlang_ru"),
        InlineKeyboardButton("🇲🇲 မြန်မာ",  callback_data="switchlang_my"),
    ]])
    await update.message.reply_text(tx(user_id, "lang_menu"), reply_markup=kb)


async def cb_switchlang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang    = query.data.split("_")[1]   # switchlang_ru → ru
    user_upsert(user_id, lang=lang)
    await query.edit_message_text(T[lang]["lang_changed"])


# ─── AI reply core ────────────────────────────────────────────────────────────
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict, user_text: str):
    user_id = update.effective_user.id
    lang    = user.get("lang") or "ru"
    name    = user.get("name") or "друг"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    history_add(user_id, "user", user_text)

    system_prompt = SYSTEM_PROMPTS[lang](name)
    messages = [{"role": "system", "content": system_prompt}]
    messages += history_get(user_id)

    try:
        resp  = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=350,
            temperature=0.9,
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        log.error("OpenAI error: %s", e)
        reply = tx(user_id, "error")

    history_add(user_id, "assistant", reply)
    await update.message.reply_text(reply, reply_markup=main_keyboard(user_id))


# ─── Main message handler ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user    = user_get(user_id)

    if not user or not user["paid"]:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(tx(user_id, "pay_btn", stars=STARS_PRICE), callback_data="pay")
        ]])
        await update.message.reply_text(
            tx(user_id, "need_pay", stars=STARS_PRICE), reply_markup=kb
        )
        return

    if not user["name"]:
        await update.message.reply_text(tx(user_id, "ask_name"))
        return

    await menu_router(update, context)


# ─── /reset command ───────────────────────────────────────────────────────────
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history_clear(user_id)
    await update.message.reply_text(
        tx(user_id, "history_cleared"),
        reply_markup=main_keyboard(user_id),
    )


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler handles start + post-payment name collection
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment),
        ],
        states={
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(conv)
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("lang",    cmd_lang))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CallbackQueryHandler(cb_setlang,    pattern=r"^setlang_"))
    app.add_handler(CallbackQueryHandler(cb_switchlang, pattern=r"^switchlang_"))
    app.add_handler(CallbackQueryHandler(cb_pay,        pattern=r"^pay$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Couple Bot started 💕")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
