import logging
import os

from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from src.router import (
    create_message_from_telegram,
    get_llm_response,
    update_bot_memory,
    get_memory_state,
    save_memory_state,
)
from src.delegates import get_online_model_response, get_claude_response


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    
    try:
        # Convert Telegram message to our Message format
        message = create_message_from_telegram(update.message.to_dict())

        # Get memory state
        memory_state = get_memory_state(chat_id)
        
        # Get router response
        router_response = get_llm_response(
            message, 
            memory_state.get("memory_content", "")
        )
        
        if isinstance(router_response, Exception):
            raise router_response
            
        assistant_messages = router_response.get("messages", [])
        
        # Send initial messages
        for msg in assistant_messages:
            await update.message.reply_text(
                escape_markdown(msg, version=2),
                parse_mode="MarkdownV2"
            )
            
        # Handle delegation if present
        if delegation := router_response.get("delegation"):
            delegate_fn = {
                "claude": get_claude_response,
                "online": get_online_model_response,
            }.get(delegation["delegate_to"])
            
            if delegate_fn:
                response = delegate_fn(
                    memory_state.get("memory_content", ""),
                    delegation["prompt"],
                )
                await update.message.reply_text(
                    escape_markdown(response, version=2),
                    parse_mode="MarkdownV2"
                )
                assistant_messages.append(response)

        # Update conversation context
        if assistant_messages:
            context_result = update_bot_memory(
                message["content"],
                assistant_messages,
                memory_state.get("memory_content", ""),
            )
            if not isinstance(context_result, Exception):
                save_memory_state(chat_id, context_result)
                    
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        await update.message.reply_text(
            "I apologize, but I encountered an error. Please try again later."
        )


if __name__ == "__main__":
    load_dotenv()

    application = Application.builder().token(os.environ["ASK_DAN_BOT_TOKEN"]).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)