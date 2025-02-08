import os
import logging
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
)

from src.handlers.message_handlers import handle_message, start_command

# Initialize environment and logging
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def main() -> None:
    """Initialize and run the bot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    application = Application.builder().token(bot_token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        handle_message
    ))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()