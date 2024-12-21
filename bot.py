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

from src.model import get_model_response, extract_dan_response

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
        
    chat_id = update.effective_chat.id
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
        
        # Stop typing indicator
        typing_stop_event.set()
        await typing_task

        final_assistant_text = updated_chat_messages[-1]['content'][0]['text']
        
        # Extract and send the response to user
        response_text = extract_dan_response(final_assistant_text, "DAN_RESPONSE")
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
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)