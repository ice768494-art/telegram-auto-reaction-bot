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
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============== CONFIGURATION ==============

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MONGO_URI = os.getenv("MONGO_URI", "").strip()
PORT = int(os.getenv("PORT", "10000"))

FORCE_SUB_CHANNEL = os.getenv(
    "FORCE_SUB_CHANNEL", "@CodeRips"
).strip()

FORCE_SUB_URL = os.getenv(
    "FORCE_SUB_URL", "https://t.me/CodeRips"
).strip()

START_IMAGE = os.getenv(
    "START_IMAGE",
    "https://i.ibb.co/8gjQJFv4/da6bee925908.jpg",
).strip()

ADMIN_IDS = {
    int(item.strip())
    for item in os.getenv("ADMIN_IDS", "").split(",")
    if item.strip().isdigit()
}

DEFAULT_EMOJIS = ["❤️", "🔥", "🥰", "😎", "👏", "🎉", "🤩"]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Render variables.")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing in Render variables.")

if not FORCE_SUB_CHANNEL or not FORCE_SUB_URL:
    raise RuntimeError("Force Subscribe variables cannot be empty.")

# ============== MONGODB ==============

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
            "reaction_count": 1,
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
    return settings_db.find_one({"_id": "global"}) or {
        "enabled": True,
        "emojis": DEFAULT_EMOJIS,
        "reaction_count": 1,
    }


def change_settings(values):
    settings_db.update_one(
        {"_id": "global"},
        {"$set": values},
        upsert=True,
    )


def increment_stat(key, amount=1):
    stats_db.update_one(
        {"_id": "global"},
        {"$inc": {key: amount}},
        upsert=True,
    )


def get_stats():
    return stats_db.find_one({"_id": "global"}) or {}


# ============== ADMIN CHECK ==============

def is_admin(update):
    user = update.effective_user
    return user is not None and user.id in ADMIN_IDS


async def admin_required(update):
    if is_admin(update):
        return True

    message = update.effective_message

    if message:
        await message.reply_text(
            "⛔ This command is for bot administrators only."
        )

    return False


# ============== RENDER HEALTH SERVER ==============

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
    try:
        server = ThreadingHTTPServer(
            ("0.0.0.0", PORT),
            HealthHandler,
        )
        logger.info("Health server running on port %s", PORT)
        server.serve_forever()

    except Exception:
        logger.exception("Health server failed")


# ============== KEYBOARDS ==============

def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Updates",
                url="https://t.me/CodeRips",
            ),
            InlineKeyboardButton(
                "💬 Support",
                url="https://t.me/Code_Rips_Support",
            ),
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📈 Statistics", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("🎭 Emojis", callback_data="emojis"),
            InlineKeyboardButton("📚 Help", callback_data="help"),
        ],
    ])


def force_sub_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Join Updates",
                url=FORCE_SUB_URL,
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ I've Joined",
                callback_data="check_subscription",
            ),
        ],
    ])


# ============== FORCE SUBSCRIBE ==============

async def check_force_sub(user_id, context):
    try:
        member = await context.bot.get_chat_member(
            chat_id=FORCE_SUB_CHANNEL,
            user_id=user_id,
        )

        return member.status in ("member", "administrator", "creator")

    except TelegramError:
        logger.exception("Membership check failed")
        return False


async def send_force_sub(chat_id, context):
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎀 <b>Welcome to Reaction Bot!</b>\n\n"
            "❤️ Please join our updates channel before using the bot.\n\n"
            "1️⃣ Press 📢 Join Updates.\n"
            "2️⃣ Join the channel.\n"
            "3️⃣ Return and press ✅ I've Joined."
        ),
        parse_mode="HTML",
        reply_markup=force_sub_menu(),
    )


# ============== ORIGINAL WELCOME MESSAGE ==============

async def send_welcome(chat_id, user, context):
    mention = (
        f'<a href="tg://user?id={user.id}">'
        f'{html.escape(user.first_name or "User")}</a>'
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

    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=START_IMAGE,
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=menu(),
        )

    except TelegramError:
        logger.exception("Could not send welcome photo")
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode="HTML",
            reply_markup=menu(),
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if user is None or chat is None:
        return

    if not await check_force_sub(user.id, context):
        await send_force_sub(chat.id, context)
        return

    await send_welcome(chat.id, user, context)


# ============== SUBSCRIPTION BUTTON ==============

async def check_subscription_button(update, context):
    query = update.callback_query

    if query is None:
        return

    joined = await check_force_sub(query.from_user.id, context)

    if not joined:
        await query.answer(
            "❌ Join the channel first, then try again.",
            show_alert=True,
        )
        return

    await query.answer("✅ Membership verified!")

    chat_id = query.message.chat_id
    user = query.from_user

    try:
        await query.message.delete()
    except TelegramError:
        logger.warning("Could not delete Force Subscribe message")

    await send_welcome(chat_id, user, context)


# ============== HELP ==============

async def help_command(update, context):
    await update.effective_message.reply_text(
        "📚 COMMANDS\n\n"
        "/start - Open welcome menu\n"
        "/help - Show commands\n"
        "/status - Bot status\n"
        "/ping - Response time\n"
        "/react - Enable reactions (admin)\n"
        "/stop - Disable reactions (admin)\n"
        "/emojis - Show emojis\n"
        "/setemoji ❤️ 🔥 🥰 - Change emojis (admin)\n"
        "/setcount 1 - Set reaction count (admin)\n"
        "/stats - Show statistics\n"
        "/test - Test a reaction on a replied-to message"
    )


# ============== STATUS & STATISTICS ==============

async def status(update, context):
    settings = get_settings()

    await update.effective_message.reply_text(
        "📊 BOT STATUS\n\n"
        f"Reactions: {'🟢 Enabled' if settings.get('enabled', True) else '🔴 Disabled'}\n"
        f"Configured emojis: {len(settings.get('emojis', DEFAULT_EMOJIS))}\n"
        f"Requested reaction count: {settings.get('reaction_count', 1)}\n"
        "Note: Telegram may limit reactions to one per message."
    )


async def stats(update, context):
    data = get_stats()

    await update.effective_message.reply_text(
        "📈 STATISTICS\n\n"
        f"Messages received: {data.get('posts_seen', 0)}\n"
        f"Successful reactions: {data.get('reactions_success', 0)}\n"
        f"Failed reactions: {data.get('reactions_failed', 0)}"
    )


async def ping(update, context):
    started = time.monotonic()
    message = await update.effective_message.reply_text("🏓 Pong!")
    elapsed = (time.monotonic() - started) * 1000
    await message.edit_text(f"🏓 Pong!\nResponse time: {elapsed:.0f} ms")


# ============== ADMIN COMMANDS ==============

async def react_command(update, context):
    if not await admin_required(update):
        return

    change_settings({"enabled": True})
    await update.effective_message.reply_text(
        "✅ Automatic reactions enabled."
    )


async def stop_command(update, context):
    if not await admin_required(update):
        return

    change_settings({"enabled": False})
    await update.effective_message.reply_text(
        "⛔ Automatic reactions disabled."
    )


async def emojis(update, context):
    settings = get_settings()
    await update.effective_message.reply_text(
        "🎭 Current emojis:\n"
        + " ".join(settings.get("emojis", DEFAULT_EMOJIS))
    )


async def setemoji(update, context):
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


async def setcount(update, context):
    if not await admin_required(update):
        return

    if len(context.args) != 1:
        await update.effective_message.reply_text(
            "Usage: /setcount 1\n"
            "The standard Telegram Bot API generally permits "
            "one reaction per message for non-Premium bots."
        )
        return

    try:
        count = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "❌ Enter a whole number."
        )
        return

    if not 1 <= count <= 10:
        await update.effective_message.reply_text(
            "❌ Choose a count from 1 to 10."
        )
        return

    change_settings({"reaction_count": count})

    await update.effective_message.reply_text(
        f"✅ Requested reaction count saved: {count}\n\n"
        "⚠️ Telegram may prevent applying multiple reactions "
        "to one message. The setting does not override Telegram limits."
    )


# ============== TEST REACTION ==============

async def test_command(update, context):
    if not await admin_required(update):
        return

    message = update.effective_message
    target = message.reply_to_message

    if target is None:
        await message.reply_text(
            "Reply to a supported message with /test."
        )
        return

    settings = get_settings()
    emoji_list = settings.get("emojis", DEFAULT_EMOJIS)

    if not emoji_list:
        await message.reply_text("❌ No emojis configured.")
        return

    emoji = random.choice(emoji_list)

    try:
        await context.bot.set_message_reaction(
            chat_id=target.chat_id,
            message_id=target.message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
        await message.reply_text(f"✅ Test reaction applied: {emoji}")

    except TelegramError:
        logger.exception("Test reaction failed")
        await message.reply_text(
            "❌ Test failed. Check the bot's permissions, "
            "the chat's reaction settings, and message type."
        )


# ============== AUTOMATIC REACTIONS ==============

async def apply_automatic_reaction(update, context):
    message = update.effective_message

    if message is None:
        return

    # Ignore private chats and bot commands.
    if message.chat.type == "private":
        return

    if message.text and message.text.startswith("/"):
        return

    increment_stat("posts_seen")

    settings = get_settings()

    if not settings.get("enabled", True):
        return

    emoji_list = settings.get("emojis", DEFAULT_EMOJIS)

    if not emoji_list:
        increment_stat("reactions_failed")
        logger.warning("No reaction emojis configured")
        return

    requested_count = max(
        1,
        min(10, int(settings.get("reaction_count", 1))),
    )

    # Select distinct emojis, but use one reaction in the standard
    # Bot API request because multiple reactions may not be supported.
    selected = random.sample(
        emoji_list,
        min(requested_count, len(emoji_list)),
    )

    emoji = selected[0]

    try:
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )

        increment_stat("reactions_success")

        logger.info(
            "Applied %s to chat %s message %s",
            emoji,
            message.chat_id,
            message.message_id,
        )

    except TelegramError:
        increment_stat("reactions_failed")
        logger.exception("Automatic reaction failed")


async def react_to_channel_post(update, context):
    # Keep the original channel-post handler behavior.
    await apply_automatic_reaction(update, context)


# ============== MENU BUTTONS ==============

async def button_handler(update, context):
    query = update.callback_query

    if query is None:
        return

    await query.answer()

    if query.data == "status":
        settings = get_settings()
        text = (
            "📊 BOT STATUS\n\n"
            f"Reactions: {'🟢 Enabled' if settings.get('enabled', True) else '🔴 Disabled'}\n"
            f"Configured emojis: {len(settings.get('emojis', DEFAULT_EMOJIS))}\n"
            f"Requested count: {settings.get('reaction_count', 1)}"
        )

    elif query.data == "stats":
        data = get_stats()
        text = (
            "📈 STATISTICS\n\n"
            f"Messages received: {data.get('posts_seen', 0)}\n"
            f"Successful reactions: {data.get('reactions_success', 0)}\n"
            f"Failed reactions: {data.get('reactions_failed', 0)}"
        )

    elif query.data == "emojis":
        settings = get_settings()
        text = (
            "🎭 Configured emojis:\n"
            + " ".join(settings.get("emojis", DEFAULT_EMOJIS))
        )

    elif query.data == "help":
        text = (
            "📚 COMMANDS\n\n"
            "/start - Open menu\n"
            "/help - Help\n"
            "/status - Status\n"
            "/ping - Ping\n"
            "/react - Enable reactions (admin)\n"
            "/stop - Disable reactions (admin)\n"
            "/emojis - Show emojis\n"
            "/setemoji ❤️ 🔥 🥰 - Set emojis (admin)\n"
            "/setcount 1 - Set requested count (admin)\n"
            "/stats - Statistics\n"
            "/test - Test reaction"
        )

    else:
        text = "Unknown button."

    await query.message.reply_text(text)


# ============== MAIN ==============

def main():
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
    application.add_handler(CommandHandler("setcount", setcount))
    application.add_handler(CommandHandler("test", test_command))

    application.add_handler(
        CallbackQueryHandler(
            check_subscription_button,
            pattern=r"^check_subscription$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(button_handler)
    )

    # Channel posts.
    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            react_to_channel_post,
        )
    )

    # Group and supergroup messages.
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            apply_automatic_reaction,
        )
    )

    logger.info("Auto Reaction Bot V2 started")

    application.run_polling(
        allowed_updates=[
            "message",
            "channel_post",
            "callback_query",
        ],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
