import os
from dotenv import load_dotenv
import logging

from telegram.ext import Application, MessageHandler, filters, CommandHandler
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

load_dotenv()

from src.chat_model import get_chat_model_response
from src.chat_history import save_chat_history, get_chat_history

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    # Check for message with either text or photo
    if not (update.message and (update.message.text or update.message.photo)):
        return
        
    chat_id = update.effective_chat.id
    
    try:
        existing_chat_history = await get_chat_history(chat_id)
        
        try:
            assistant_response = await get_chat_model_response(update.message, existing_chat_history)
            await update.message.reply_chat_action(ChatAction.TYPING)
            await update.message.reply_text(
                markdownify(assistant_response),
                parse_mode="MarkdownV2"
            )

            # Update chat history
            updated_history = (existing_chat_history if existing_chat_history else []) + [
                {"role": "user", "parts": update.message.text or update.message.caption or ""},
                {"role": "model", "parts": assistant_response}
            ]
            await save_chat_history(chat_id, updated_history)
                
        except Exception as e:
            logging.error(f"Error getting model response: {str(e)}")
            await update.message.reply_text(
                "I apologize, but I encountered an error processing your request. Please try again later."
            )
            
    except Exception as e:
        logging.exception("Error accessing chat history")
        await update.message.reply_text(
            "I apologize, but I encountered an error accessing the chat history. Please try again later."
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