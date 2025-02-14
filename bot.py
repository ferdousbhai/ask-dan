import os
import logging
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram import Update


# Initialize environment and logging
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def main() -> None:
    """Initialize and run the bot."""
    from src.command_handlers import start_command
    from src.message_handler import handle_message

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    application = Application.builder().token(bot_token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))

    # Define supported document types
    document_filter = (
        filters.Document.PDF |  # PDF files
        filters.Document.TXT |  # Text files
        filters.Document.MimeType("text/plain") |  # Plain text
        filters.Document.MimeType("text/markdown") |  # Markdown files
        filters.Document.MimeType("text/csv")  # CSV files
    )

    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE |
        filters.AUDIO | document_filter | filters.LOCATION) & ~filters.COMMAND,
        handle_message
    ))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()