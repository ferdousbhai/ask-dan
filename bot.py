import os
from dotenv import load_dotenv
import logging
from telegram.ext import Application, MessageHandler, filters, CommandHandler
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify
import asyncio

load_dotenv()

from src.claude import get_model_response, extract_dan_response
from src.credit_manager import (
    check_credits, deduct_credit, get_user_credits,
    get_all_credits, set_user_credits, reset_all_credits,
    is_admin
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# In-memory mapping of chat history by chat id
chat_history_by_chat_id = {}

async def show_typing_indicator(chat, stop_event):
    """Keep showing typing indicator until stop_event is set."""
    while not stop_event.is_set():
        await chat.send_chat_action(ChatAction.TYPING)
        # Chat action expires after 5 seconds, so we refresh it every 4 seconds
        await asyncio.sleep(4)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not (update.message and (update.message.text or update.message.photo)):
        return

    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username

    # Check credits before processing
    has_credits, message = check_credits(chat_id, username)
    if not has_credits:
        await update.message.reply_text(message)
        return

    chat_history = chat_history_by_chat_id.get(chat_id, [])

    # Create an event to control the typing indicator
    typing_stop_event = asyncio.Event()

    # Start typing indicator in the background
    typing_task = asyncio.create_task(
        show_typing_indicator(update.effective_chat, typing_stop_event)
    )

    try:
        updated_chat_messages = await get_model_response(
            update.message,
            chat_history=chat_history
        )
        if isinstance(updated_chat_messages, Exception):
            raise updated_chat_messages

        # Deduct credit after successful API call
        deduct_credit(chat_id, username)

        # Stop typing indicator
        typing_stop_event.set()
        await typing_task

        final_assistant_text = updated_chat_messages[-1]['content'][0]['text']

        # Extract and send the response to user
        try:
            response_text = extract_dan_response(final_assistant_text, "DAN_RESPONSE")
            if "<DAN_RESPONSE>" not in final_assistant_text:
                logging.warning(f"Response missing DAN_RESPONSE tags: {final_assistant_text[:100]}...")
        except Exception as e:
            logging.error(f"Error extracting response: {str(e)}")
            response_text = final_assistant_text

        await update.message.reply_text(
            markdownify(response_text),
            parse_mode="MarkdownV2"
        )

        chat_history_by_chat_id[chat_id] = updated_chat_messages

    except Exception as e:
        # Stop typing indicator in case of error
        typing_stop_event.set()
        await typing_task

        logging.error(f"Error getting model response: {str(e)}")
        logging.exception("Full traceback:")
        await update.message.reply_text(
            "I apologize, but I encountered an error processing your request. Please try again later."
        )

async def start_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("👋")

async def credits_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /credits command."""
    chat_id = str(update.effective_chat.id)
    credits_info = get_user_credits(chat_id)
    if credits_info:
        await update.message.reply_text(
            f"You have {credits_info['calls_remaining']} calls remaining this month."
        )
    else:
        await update.message.reply_text("No credit information found.")

async def credits_all_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /credits_all command (admin only)."""
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("This command is only available to admins.")
        return

    credits = get_all_credits()
    message = "Credits for all users:\n\n"
    for chat_id, info in credits.items():
        message += f"Chat ID: {chat_id}\n"
        message += f"Username: {info['username']}\n"
        message += f"Calls remaining: {info['calls_remaining']}\n"
        message += f"Last reset: {info['last_reset']}\n\n"

    await update.message.reply_text(message)

async def set_credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set_credits command (admin only)."""
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("This command is only available to admins.")
        return

    try:
        chat_id, amount = context.args
        set_user_credits(chat_id, int(amount))
        await update.message.reply_text(f"Credits for {chat_id} set to {amount}")
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /set_credits <chat_id> <amount>")

async def reset_credits_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset_credits command (admin only)."""
    if not is_admin(update.effective_user.username):
        await update.message.reply_text("This command is only available to admins.")
        return

    reset_all_credits()
    await update.message.reply_text("All credits have been reset to 10.")

if __name__ == "__main__":
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

    # Create application
    application = Application.builder().token(bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))

    # Add message handler
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        handle_message
    ))

    # Add credit-related command handlers
    application.add_handler(CommandHandler("credits", credits_command))
    application.add_handler(CommandHandler("credits_all", credits_all_command))
    application.add_handler(CommandHandler("set_credits", set_credits_command))
    application.add_handler(CommandHandler("reset_credits", reset_credits_command))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)