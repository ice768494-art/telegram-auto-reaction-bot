import os
import random
import logging

from telegram import Update, ReactionTypeEmoji
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

BOT_TOKEN = os.environ["BOT_TOKEN"]

EMOJIS = ["❤️", "🔥", "🥰", "😎", "👏", "🎉", "🤩"]

async def auto_react(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.channel_post

    if not message:
        return

    try:
        count = min(3, len(EMOJIS))
        selected = random.sample(EMOJIS, count)

        # Telegram's API accepts a list of reactions,
        # subject to channel and API restrictions.
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
            "Reacted to channel post %s with %s",
            message.message_id,
            selected,
        )

    except Exception:
        logging.exception("Could not react to channel post")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            auto_react,
        )
    )

    logging.info("Auto Reaction Bot started")
    app.run_polling(
        allowed_updates=["channel_post"],
    )

if __name__ == "__main__":
    main()
