import logging
import asyncio
import re
from telegram import Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from src.model.claude import chat_with_model
from src.model.prompt import get_system_prompt
from src.utils.telegram_utils import show_typing_indicator, create_user_message

logger = logging.getLogger(__name__)

# Type definitions
ChatHistory = list[dict]
ChatHistoryMap = dict[int, ChatHistory]

# In-memory chat history storage
chat_history_by_chat_id: ChatHistoryMap = {}

async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages from users."""
    if not update.message or not (update.message.text or update.message.photo):
        return

    chat_id = update.effective_chat.id
    chat_history = chat_history_by_chat_id.get(chat_id, [])
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(show_typing_indicator(update.effective_chat, stop_typing_event))

    try:
        user_message = await create_user_message(update.message)
        model_response = await chat_with_model(
            user_message=user_message,
            system_prompt=get_system_prompt(update.message),
            chat_history=chat_history
        )

        # Early return if model_response is an Exception
        if isinstance(model_response, Exception):
            raise model_response

        # Store chat history before processing response
        chat_history_by_chat_id[chat_id] = model_response

        # Get response text from the last message
        response_text = model_response[-1]['content'][0]['text'].strip()

        # Remove think tags and contents in think tags if present
        response_text = re.sub(r'<think>[\s\S]*?</think>', '', response_text)

        # Split response into paragraphs and send them separately
        paragraphs = [p.strip() for p in response_text.split('\n\n') if p.strip()]
        for paragraph in paragraphs:
            if paragraph:
                await update.message.reply_text(
                    markdownify(paragraph),
                    parse_mode="MarkdownV2"
                )

    except Exception as e:
        logger.error(f"Error in message handler: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "I apologize, but I encountered an error processing your request. "
            "Please try again later or contact @ferdousbhai for support."
        )
    finally:
        stop_typing_event.set()
        await typing_task

async def start_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text("👋")