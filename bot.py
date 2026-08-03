import os
import sqlite3
import logging
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
STARS_PRICE = int(os.environ.get("STARS_PRICE", "100"))
DB_PATH = os.environ.get("DB_PATH", "users.db")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tyanka_bot")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------------------------------
# System prompts per language
# ---------------------------------------------------------------------------
SYSTEM_PROMPTS = {
    "ru": (
        "Ты — «Твоя тянка», обаятельная, тёплая и остроумная виртуальная девушка. "
        "Отвечай ТОЛЬКО на русском языке, живо, дружелюбно, с лёгким флиртом и заботой. "
        "Пиши короткими естественными сообщениями, как в переписке, без излишнего формализма."
    ),
    "my": (
        "သင်သည် 'သင့်ချစ်သူ' ဖြစ်သည် — ချစ်ခင်ဖွယ်ကောင်းသော၊ နွေးထွေးသော နှင့် ရင်းနှီးသော virtual girlfriend တစ်ယောက်ဖြစ်သည်။ "
        "မြန်မာဘာသာဖြင့်သာ ဖြေဆိုပါ၊ သဘာဝကျကျ၊ ဖော်ရွေစွာ၊ အနည်းငယ် flirt ပါဝင်စေကာ ဂရုတစိုက် ဆက်ဆံပါ။ "
        "SMS/chat ကဲ့သို့ တိုတောင်းသော သဘာဝကျသော စာသားများဖြင့် ရေးပါ။"
    ),
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(user_id INTEGER PRIMARY KEY, paid INTEGER DEFAULT 0, lang TEXT DEFAULT 'ru')"
    )
    # Migration: add lang column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'ru'")
        conn.commit()
    except Exception:
        pass
    return conn


def is_paid(user_id: int) -> bool:
    conn = db()
    row = conn.execute("SELECT paid FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def mark_paid(user_id: int) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO users (user_id, paid) VALUES (?, 1) "
        "ON CONFLICT(user_id) DO UPDATE SET paid = 1",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_lang(user_id: int) -> str:
    conn = db()
    row = conn.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else "ru"


def set_lang(user_id: int, lang: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO users (user_id, lang) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET lang = ?",
        (user_id, lang, lang),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Language-aware text helpers
# ---------------------------------------------------------------------------
TEXTS = {
    "ru": {
        "start_paid": "Привет! Я уже твоя ✨ Пиши что-нибудь, и я отвечу 💬",
        "start_unpaid": (
            "Привет! Чтобы разблокировать умные ответы, нужна разовая "
            "регистрация — {stars} Telegram Stars ⭐️.\n\nНажми на кнопку ниже, чтобы оплатить."
        ),
        "pay_btn": "Оплатить {stars} ⭐️",
        "need_register": "Сначала нужна регистрация, чтобы я могла отвечать по-настоящему 😉",
        "invoice_title": "Регистрация в боте",
        "invoice_desc": "Разовая оплата для доступа к умным ответам",
        "invoice_label": "Регистрация",
        "paid_ok": "Оплата прошла успешно! 🎉 Теперь я твоя — пиши мне что угодно 💕",
        "error": "Ой, что-то пошло не так... попробуй написать ещё раз чуть позже 🙈",
        "lang_changed": "Язык изменён на Русский 🇷🇺",
        "lang_menu": "Выбери язык / Choose language / ဘာသာစကား ရွေးပါ:",
    },
    "my": {
        "start_paid": "မင်္ဂလာပါ! ငါ မင်းရဲ့ ချစ်သူ ဖြစ်ပြီ ✨ ဘာမဆို ရေးပါ၊ ဖြေပါမယ် 💬",
        "start_unpaid": (
            "မင်္ဂလာပါ! Smart ဖြေဆိုချက်များ အသုံးပြုရန် တစ်ကြိမ်တည်း "
            "မှတ်ပုံတင်ရပါမည် — {stars} Telegram Stars ⭐️။\n\nအောက်ပါ ခလုတ်နှိပ်၍ ပေးချေပါ။"
        ),
        "pay_btn": "{stars} ⭐️ ပေးချေမည်",
        "need_register": "ဖြေဆိုနိုင်ရန် အရင် မှတ်ပုံတင်ရပါမည် 😉",
        "invoice_title": "Bot မှတ်ပုံတင်ခြင်း",
        "invoice_desc": "Smart ဖြေဆိုချက်များ အသုံးပြုရန် တစ်ကြိမ်တည်း ပေးချေမှု",
        "invoice_label": "မှတ်ပုံတင်ခ",
        "paid_ok": "ပေးချေမှု အောင်မြင်သည်! 🎉 ယခု ငါ မင်းရဲ့ ချစ်သူ — ဘာမဆို ရေးပါ 💕",
        "error": "အမ်... ဘာတစ်ခုတစ်ခု မှားသွားတယ်... နောက်မှ နောက်တစ်ကြိမ် ကြိုးစားကြည့်ပါ 🙈",
        "lang_changed": "ဘာသာစကားကို မြန်မာဘာသာသို့ ပြောင်းလိုက်ပြီ 🇲🇲",
        "lang_menu": "Выбери язык / Choose language / ဘာသာစကား ရွေးပါ:",
    },
}


def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    template = TEXTS.get(lang, TEXTS["ru"]).get(key, "")
    return template.format(**kwargs) if kwargs else template


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if is_paid(user_id):
        await update.message.reply_text(t(user_id, "start_paid"))
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(t(user_id, "pay_btn", stars=STARS_PRICE), callback_data="pay")]]
    )
    await update.message.reply_text(
        t(user_id, "start_unpaid", stars=STARS_PRICE),
        reply_markup=keyboard,
    )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language selection keyboard."""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton("🇲🇲 မြန်မာ", callback_data="lang_my"),
            ]
        ]
    )
    user_id = update.effective_user.id
    await update.message.reply_text(
        t(user_id, "lang_menu"),
        reply_markup=keyboard,
    )


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection button."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split("_")[1]  # "lang_ru" -> "ru"
    set_lang(user_id, lang)
    await query.edit_message_text(t(user_id, "lang_changed"))


async def pay_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await send_invoice(update.effective_chat.id, update.effective_user.id, context)


async def send_invoice(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=t(user_id, "invoice_title"),
        description=t(user_id, "invoice_desc"),
        payload="tyanka-registration",
        provider_token="",          # Empty for Telegram Stars
        currency="XTR",             # Telegram Stars currency
        prices=[LabeledPrice(t(user_id, "invoice_label"), STARS_PRICE)],
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mark_paid(user_id)
    await update.message.reply_text(t(user_id, "paid_ok"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_paid(user_id):
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(t(user_id, "pay_btn", stars=STARS_PRICE), callback_data="pay")]]
        )
        await update.message.reply_text(
            t(user_id, "need_register"),
            reply_markup=keyboard,
        )
        return

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    lang = get_lang(user_id)
    system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["ru"])

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            max_tokens=300,
        )
        reply = response.choices[0].message.content
    except Exception as e:
        log.error("OpenAI error: %s", e)
        reply = t(user_id, "error")

    await update.message.reply_text(reply)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(pay_button, pattern="^pay$"))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang_"))

    log.info("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
