import os
import random
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReactionTypeEmoji
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

# ========== CONFIGURATION ==========

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

EMOJI_LIST = [
    emoji.strip()
    for emoji in os.environ.get(
        "EMOJI_LIST",
        "❤️,🔥,🥰,😎,👏,🎉,🤩"
    ).split(",")
    if emoji.strip()
]

PORT = int(os.environ.get("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ========== RENDER HEALTH SERVER ==========

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

    def log_message(self, format, *args):
        pass


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health server started on port %s", PORT)
    server.serve_forever()


# ========== AUTO REACTION ==========

async def react_to_channel_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    post = update.channel_post

    if post is None:
        return

    if not EMOJI_LIST:
        logger.error("EMOJI_LIST is empty")
        return

    selected_emoji = random.choice(EMOJI_LIST)

    try:
        await context.bot.set_message_reaction(
            chat_id=post.chat_id,
            message_id=post.message_id,
            reaction=[
                ReactionTypeEmoji(emoji=selected_emoji)
            ],
        )

        logger.info(
            "Reacted with %s to channel post %s",
            selected_emoji,
            post.message_id,
        )

    except Exception:
        logger.exception(
            "Could not react to channel post %s",
            post.message_id,
        )


# ========== MAIN ==========

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add it in Render Environment Variables."
        )

    threading.Thread(
        target=start_health_server,
        daemon=True,
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            react_to_channel_post,
        )
    )

    logger.info("Auto Reaction Bot is starting...")

    application.run_polling(
        allowed_updates=["channel_post"],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
