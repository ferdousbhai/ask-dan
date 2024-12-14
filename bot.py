import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from modal import Dict
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from src.message_handler import create_message_from_telegram
from src.model import get_model_response, MemoryState, get_new_bot_memory

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

memory_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)

async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    # Create message object from the update
    user_message = create_message_from_telegram(update.message)
    if not user_message or user_message.content.type != "text":  # Only handle text messages for now
        return

    chat_id = update.effective_chat.id
    
    try:
        # Get existing memory
        existing_memory_data = None
        if memory_data := memory_dict.get(chat_id):
            try:
                existing_memory_data = MemoryState(**memory_data)
            except Exception:
                logging.exception("Error deserializing memory state")
        
        # Get and send model response
        if response := get_model_response(user_message, existing_memory_data):
            if isinstance(response, Exception):
                raise response
                
            await update.message.reply_text(
                markdownify(response),
                parse_mode="MarkdownV2"
            )

            # Update conversation memory
            if new_memory := get_new_bot_memory(
                existing_memory_data,
                user_message.content.text,  # Changed to access text from content
                [response],
            ):
                if isinstance(new_memory, Exception):
                    raise new_memory
                    
                memory_dict[chat_id] = MemoryState(
                    memory_content=new_memory,
                    created_at=datetime.now(timezone.utc)
                ).model_dump()
                
    except Exception:
        logging.exception("Error processing message")
        await update.message.reply_text(
            "I apologize, but I encountered an error. Please try again later."
        )


if __name__ == "__main__":
    load_dotenv()
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)