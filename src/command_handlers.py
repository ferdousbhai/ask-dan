from telegram import Update
from telegram.ext import ContextTypes

async def start_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text("👋")