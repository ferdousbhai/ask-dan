import os
import logging
import asyncio
import re
import base64
from dotenv import load_dotenv
from telegram import Update, Chat, Message as TelegramMessage
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from telegram.constants import ChatAction
from telegramify_markdown import markdownify

from model.claude import chat_with_model
from model.prompt import get_system_prompt


# Initialize environment and logging
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Type definitions
ChatHistory = list[dict]
ChatHistoryMap = dict[int, ChatHistory]

# In-memory chat history storage
chat_history_by_chat_id: ChatHistoryMap = {}

async def show_typing_indicator(chat: Chat, stop_event: asyncio.Event) -> None:
    """
    Show and maintain a typing indicator until the stop event is set.

    Args:
        chat: The Telegram chat to show the indicator in
        stop_event: Event to control when to stop showing the indicator
    """
    while not stop_event.is_set():
        await chat.send_chat_action(ChatAction.TYPING)
        # Chat action expires after 5 seconds, so refresh every 4 seconds
        await asyncio.sleep(4)

async def create_user_message(telegram_message: TelegramMessage) -> dict:
    """Create a complete user message from a Telegram message, handling both images and text.

    Args:
        telegram_message: The Telegram message to process

    Returns:
        A complete user message in Claude's format with role and content
    """
    content_blocks = []

    # Add image if it exists
    if telegram_message.photo:
        photo = telegram_message.photo[-1]
        image_bytes = await (await photo.get_file()).download_as_bytearray()
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode('utf-8'),
            }
        })

    # Add text if it exists
    if message_text := telegram_message.text or telegram_message.caption:
        content_blocks.append({
            "type": "text",
            "text": message_text
        })

    return {"role": "user", "content": content_blocks}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming messages from users.

    Args:
        update: The incoming update from Telegram
        context: The context for this update
    """
    if not update.message or not (update.message.text or update.message.photo):
        return

    chat_id = update.effective_chat.id
    chat_history = chat_history_by_chat_id.get(chat_id, [])

    # Setup typing indicator
    typing_task = asyncio.create_task(
        show_typing_indicator(update.effective_chat, typing_event := asyncio.Event())
    )

    try:
        # Get model response
        user_message = await create_user_message(update.message)
        model_response: list[dict] | Exception = await chat_with_model(
            user_message=user_message,
            system_prompt=get_system_prompt(update.message),
            chat_history=chat_history,
            telegram_update=update,
            telegram_context=context
        )
        if isinstance(model_response, Exception):
            raise model_response

        # Get the final assistant text
        final_assistant_text = model_response[-1]['content'][0]['text']
        # Remove all thinking-related text and tags
        response_text = re.sub(r'<think>[\s\S]*?</think>', '', final_assistant_text).strip()

        # Send response
        await update.message.reply_text(
            markdownify(response_text),
            parse_mode="MarkdownV2"
        )

        # Update chat history
        chat_history_by_chat_id[chat_id] = model_response

    except Exception as e:
        logger.error(f"Error getting model response: {str(e)}")
        logger.exception("Full traceback:")
        await update.message.reply_text(
            "I apologize, but I encountered an error processing your request. Please report this to the developer @ferdousbhai or try again later."
        )
    finally:
        # Always ensure typing indicator is stopped
        typing_event.set()
        await typing_task

async def start_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text("👋")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    if query.data.startswith("show_research_"):
        message_id = query.data.split("_")[2]
        research_result = context.user_data.get(f"research_{message_id}")
        if research_result:
            # Edit the original message instead of sending a new one
            await query.message.edit_text(
                text=markdownify(research_result),
                parse_mode='MarkdownV2'
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
    application.add_handler(CallbackQueryHandler(handle_button))

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
