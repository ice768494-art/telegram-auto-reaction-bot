import os
import time
import random
import logging
import threading
import html 
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pymongo import MongoClient
from telegram import (
    Update,
    ReactionTypeEmoji,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =============== CONFIGURATION ===============

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
FORCE_SUB_CHANNEL = "@CodeRips"
FORCE_SUB_URL = "https://t.me/CodeRips"
MONGO_URI = os.getenv("MONGO_URI", "").strip()
PORT = int(os.getenv("PORT", "10000"))

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

DEFAULT_EMOJIS = ["❤️", "🔥", "🥰", "😎", "👏", "🎉", "🤩"]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =============== DATABASE ===============

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
    

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing.")

mongo_client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000,
)
db = mongo_client["auto_reaction_bot"]
settings_db = db["settings"]
stats_db = db["stats"]

settings_db.update_one(
    {"_id": "global"},
    {
        "$setOnInsert": {
            "enabled": True,
            "emojis": DEFAULT_EMOJIS,
        }
    },
    upsert=True,
)

stats_db.update_one(
    {"_id": "global"},
    {
        "$setOnInsert": {
            "posts_seen": 0,
            "reactions_success": 0,
            "reactions_failed": 0,
        }
    },
    upsert=True,
)


def get_settings():
    return settings_db.find_one({"_id": "global"})


def change_settings(values):
    settings_db.update_one(
        {"_id": "global"},
        {"$set": values},
        upsert=True,
    )


def increment_stat(key, value=1):
    stats_db.update_one(
        {"_id": "global"},
        {"$inc": {key: value}},
        upsert=True,
    )


def is_admin(update: Update):
    user = update.effective_user
    return user is not None and user.id in ADMIN_IDS


async def admin_required(update: Update):
    if is_admin(update):
        return True

    await update.effective_message.reply_text(
        "⛔ This command is available to bot administrators only."
    )
    return False


# =============== RENDER HEALTH SERVER ===============

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Auto Reaction Bot is running!")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def start_health_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health server running on port %s", PORT)
    server.serve_forever()


# =============== MENU ===============

# =============== CUSTOM START MENU ===============

START_IMAGE = "https://i.ibb.co/8gjQJFv4/da6bee925908.jpg"


def menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "📢 Updates",
                url="https://t.me/CodeRips"
            ),
            InlineKeyboardButton(
                "💬 Support",
                url="https://t.me/Code_Rips_Support"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 Status",
                callback_data="status"
            ),
            InlineKeyboardButton(
                "📈 Statistics",
                callback_data="stats"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎭 Emojis",
                callback_data="emojis"
            ),
            InlineKeyboardButton(
                "📚 Help",
                callback_data="help"
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)

async def check_force_sub(user_id, context):
    try:
        member = await context.bot.get_chat_member(
            chat_id=FORCE_SUB_CHANNEL,
            user_id=user_id,
        )

        return member.status in (
            "member",
            "administrator",
            "creator",
        )

    except Exception:
        logger.exception("Force-subscription check failed")
        return False

def force_sub_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "📢 Join Updates",
                url=FORCE_SUB_URL,
            )
        ],
        [
            InlineKeyboardButton(
                "✅ I've Joined",
                callback_data="check_subscription",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if user is None:
        return

    joined = await check_force_sub(user.id, context)

    if not joined:
        await update.effective_message.reply_text(
            "🎀 Welcome!\n\n"
            "Please join our updates channel to use this bot. ❤️",
            reply_markup=force_sub_menu(),
        )
        return

    mention = (
        f'<a href="tg://user?id={user.id}">'
        f'{html.escape(user.first_name)}</a>'
    )

    welcome_text = (
        f"🎀 <b>𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {mention}</b>\n\n"
        "𝖳𝗁𝖺𝗇𝗄 𝗒𝗈𝗎 𝖿𝗈𝗋 𝗌𝗍𝖺𝗋𝗍𝗂𝗇𝗀 𝗍𝗁𝖾 𝖻𝗈𝗍 ✨\n\n"
        "🤖 <b>𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝗧𝗼 𝗥𝗲𝗮𝗰𝘁𝗶𝗼𝗻 𝗕𝗼𝘁</b>\n\n"
        "💬 <b>𝗜𝗻𝗳𝗼:</b>\n"
        "• <b>𝗣𝗿𝗶𝘃𝗮𝘁𝗲 𝗖𝗵𝗮𝘁:</b> "
        "𝖨 𝖼𝖺𝗇 𝗋𝖾𝖺𝖼𝗍 𝗍𝗈 𝗒𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾𝗌.\n"
        "• <b>𝗚𝗿𝗼𝘂𝗽𝘀 & 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀:</b> "
        "𝖠𝖽𝖽 𝗆𝖾 𝗍𝗈 𝗀𝗋𝗈𝗎𝗉𝗌 𝗈𝗋 𝖼𝗁𝖺𝗇𝗇𝖾𝗅𝗌 "
        "𝗍𝗈 𝖾𝗇𝖺𝖻𝗅𝖾 𝗋𝖾𝖺𝖼𝗍𝗂𝗈𝗇𝗌.\n\n"
        "😶‍🌫️ 𝖴𝗌𝖾 𝗍𝗁𝖾 𝖻𝗎𝗍𝗍𝗈𝗇𝗌 𝖻𝖾𝗅𝗈𝗐 "
        "𝗍𝗈 𝖾𝗑𝗉𝗅𝗈𝗋𝖾 𝗆𝗈𝗋𝖾."
    )

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=START_IMAGE,
        caption=welcome_text,
        parse_mode="HTML",
        reply_markup=menu(),
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=START_IMAGE,
        caption=welcome_text,
        parse_mode="HTML",
        reply_markup=menu(),
    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📚 COMMANDS\n\n"
        "/start - Open the menu\n"
        "/help - Show commands\n"
        "/status - Check bot status\n"
        "/ping - Check response time\n"
        "/react - Enable automatic reactions\n"
        "/stop - Disable automatic reactions\n"
        "/emojis - View reaction emojis\n"
        "/setemoji ❤️ 🔥 🥰 - Change emojis\n"
        "/stats - Show statistics\n"
        "/test - Test a reaction on a replied-to message\n\n"
        "The bot reacts to new posts in channels where it is an admin."
    )


# =============== STATUS AND STATS ===============

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_settings()
    await update.effective_message.reply_text(
        "📊 BOT STATUS\n\n"
        f"Reactions: {'🟢 Enabled' if settings['enabled'] else '🔴 Disabled'}\n"
        f"Emojis configured: {len(settings['emojis'])}\n"
        "Database: Connected"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = stats_db.find_one({"_id": "global"}) or {}
    await update.effective_message.reply_text(
        "📈 REACTION STATISTICS\n\n"
        f"Posts received: {data.get('posts_seen', 0)}\n"
        f"Successful reactions: {data.get('reactions_success', 0)}\n"
        f"Failed reactions: {data.get('reactions_failed', 0)}"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    started = time.monotonic()
    message = await update.effective_message.reply_text("🏓 Pong!")
    elapsed = (time.monotonic() - started) * 1000
    await message.edit_text(f"🏓 Pong!\nResponse time: {elapsed:.0f} ms")


# =============== ADMIN COMMANDS ===============

async def react_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_required(update):
        return

    change_settings({"enabled": True})
    await update.effective_message.reply_text(
        "✅ Automatic reactions enabled."
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_required(update):
        return

    change_settings({"enabled": False})
    await update.effective_message.reply_text(
        "⛔ Automatic reactions disabled."
    )


async def emojis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_settings()
    await update.effective_message.reply_text(
        "🎭 Current emojis:\n" + " ".join(settings["emojis"])
    )


async def setemoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_required(update):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /setemoji ❤️ 🔥 🥰 😎"
        )
        return

    selected = list(dict.fromkeys(context.args))

    if len(selected) > 50:
        await update.effective_message.reply_text(
            "❌ Please use 50 emojis or fewer."
        )
        return

    change_settings({"emojis": selected})

    await update.effective_message.reply_text(
        "✅ Reaction emojis updated:\n" + " ".join(selected)
    )


# =============== TEST REACTION ===============

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_required(update):
        return

    message = update.effective_message
    target = message.reply_to_message

    if target is None:
        await message.reply_text(
            "Reply to a channel post or supported message with /test."
        )
        return

    settings = get_settings()
    emoji = random.choice(settings["emojis"])

    try:
        await context.bot.set_message_reaction(
            chat_id=target.chat_id,
            message_id=target.message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
        await message.reply_text(f"✅ Test reaction applied: {emoji}")

    except Exception as exc:
        logger.exception("Test reaction failed")
        await message.reply_text(f"❌ Test failed: {exc}")


# =============== AUTOMATIC REACTIONS ===============

async def react_to_channel_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    post = update.channel_post

    if post is None:
        return

    increment_stat("posts_seen")

    settings = get_settings()

    if not settings or not settings.get("enabled", True):
        return

    emojis = settings.get("emojis", DEFAULT_EMOJIS)

    if not emojis:
        logger.warning("No reaction emojis configured")
        return

    # Telegram permits bots to set only one reaction
    # per message using setMessageReaction.
    emoji = random.choice(emojis)

    try:
        await context.bot.set_message_reaction(
            chat_id=post.chat_id,
            message_id=post.message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )

        increment_stat("reactions_success")

        logger.info(
            "Reaction %s applied to chat %s message %s",
            emoji,
            post.chat_id,
            post.message_id,
        )

    except Exception:
        increment_stat("reactions_failed")
        logger.exception("Failed to react to channel post")


# =============== INLINE BUTTONS ===============
async def check_subscription_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    joined = await check_force_sub(
        query.from_user.id,
        context,
    )

    if joined:
        await query.message.delete()

        await query.message.chat.send_message(
            "✅ Subscription verified! Now send /start."
        )
    else:
        await query.answer(
            "❌ Please join @CodeRips first!",
            show_alert=True,
        )

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    if query.data == "status":
        settings = get_settings()
        text = (
            f"Reactions: {'Enabled' if settings['enabled'] else 'Disabled'}\n"
            f"Configured emojis: {len(settings['emojis'])}"
        )

    elif query.data == "stats":
        data = stats_db.find_one({"_id": "global"}) or {}
        text = (
            f"Posts received: {data.get('posts_seen', 0)}\n"
            f"Successful reactions: {data.get('reactions_success', 0)}\n"
            f"Failed reactions: {data.get('reactions_failed', 0)}"
        )

    elif query.data == "emojis":
        settings = get_settings()
        text = "Configured emojis:\n" + " ".join(settings["emojis"])

    else:
        text = (
            "Commands:\n/start /help /status /ping\n"
            "/react /stop /emojis /setemoji /stats /test"
        )

    await query.message.reply_text(text)


# =============== MAIN ===============

def main():
    # Fail early if the MongoDB URI is invalid or unreachable.
    mongo_client.admin.command("ping")
    logger.info("MongoDB connection successful")

    threading.Thread(
        target=start_health_server,
        daemon=True,
    ).start()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("react", react_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("emojis", emojis))
    application.add_handler(CommandHandler("setemoji", setemoji))
    application.add_handler(CommandHandler("test", test_command))

    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            react_to_channel_post,
        )
    )

    logger.info("Auto Reaction Bot started")

    application.run_polling(
        allowed_updates=["message", "channel_post", "callback_query"],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
