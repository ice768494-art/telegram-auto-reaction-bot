import os
import random
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import ReactionTypeEmoji, Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------- CONFIGURATION ----------

BOT_TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "10000"))

EMOJIS = ["❤️", "🔥", "🥰", "😎", "👏", "🎉", "🤩"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ---------- HEALTH CHECK SERVER ----------

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auto Reaction Bot is running!")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logging.info("Health server listening on port %s", PORT)
    server.serve_forever()


# ---------- AUTO REACTION ----------

async def auto_react(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.channel_post

    if message is None:
        return

    async def auto_react(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.channel_post

    if message is None:
        return

    emoji = random.choice(EMOJIS)

    try:
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[
                ReactionTypeEmoji(emoji=emoji)
            ],
            is_big=False,
        )

        logging.info(
            "Reaction added to post %s: %s",
            message.message_id,
            emoji,
        )

    except Exception:
        logging.exception(
            "Could not react to post %s",
            message.message_id,
        )
    message = update.channel_post

    if message is None:
        return

    selected = random.sample(EMOJIS, 1)

    try:
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[
                ReactionTypeEmoji(emoji=emoji)
                for emoji in selected
            ],
            is_big=False,
        )

        logging.info(
            "Reaction added to post %s: %s",
            message.message_id,
            selected,
        )

    except Exception:
        logging.exception(
            "Could not react to post %s",
            message.message_id,
        )

    try:
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[
                ReactionTypeEmoji(emoji=emoji)
                for emoji in selected
            ],
            is_big=False,
        )

        logging.info(
            "Reactions set on post %s: %s",
            message.message_id,
            selected,
        )

    except Exception:
        logging.exception(
            "Could not react to post %s",
            message.message_id,
        )


# ---------- START BOT ----------

def main():
    threading.Thread(
        target=start_web_server,
        daemon=True,
    ).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            auto_react,
        )
    )

    logging.info("Auto Reaction Bot starting")

    app.run_polling(
        allowed_updates=["channel_post"],
    )


if __name__ == "__main__":
    main()
