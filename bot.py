import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from src.model import get_model_response, MemoryState, get_new_bot_memory
from src.database import init_db, save_memory, get_memory

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Add startup action
async def post_init(_: Application) -> None:
    await init_db()

# Handle incoming messages
async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    
    try:
        existing_memory_data = await get_memory(chat_id)
        
        if assistant_response := await get_model_response(update.message, existing_memory_data):
            if isinstance(assistant_response, Exception):
                raise assistant_response
                
            await update.message.reply_text(
                markdownify(assistant_response),
                parse_mode="MarkdownV2"
            )

            # Update conversation memory
            if new_memory := await get_new_bot_memory(
                existing_memory_data,
                update.message,
                assistant_response,
            ):
                if isinstance(new_memory, Exception):
                    raise new_memory
                    
                await save_memory(
                    chat_id,
                    MemoryState(
                        memory_content=new_memory,
                        created_at=datetime.now(timezone.utc)
                    )
                )
                
    except Exception:
        logging.exception("Error processing message")
        await update.message.reply_text(
            "I apologize, but I encountered an error. Please try again later."
        )

if __name__ == "__main__":
    load_dotenv()
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add startup action
    application.post_init = post_init  
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)