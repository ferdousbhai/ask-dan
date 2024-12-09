import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from modal import Dict
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify

from src.message_handler import create_message_from_telegram, Message
from src.router import get_router_response, RouterResponse
from src.delegates import get_online_model_response, get_claude_response
from src.memory import get_new_bot_memory, MemoryState

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

memory_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)

async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    assistant_messages = []
    
    try:
        telegram_message_dict = update.message.to_dict()
        user_message: Message = create_message_from_telegram(telegram_message_dict)
        
        # When retrieving memory
        memory_dict_data = memory_dict.get(chat_id)
        existing_memory_data: MemoryState | None = (
            MemoryState(**memory_dict_data) if memory_dict_data else None
        )
        
        router_response: RouterResponse = get_router_response(user_message, existing_memory_data)
        if isinstance(router_response, Exception):
            logging.error(f"Router error: {str(router_response)}")
            await update.message.reply_text(
                "I'm having trouble processing your request. Please try again."
            )
            return
            
        # Send and collect router messages if present
        if router_response.messages:
            assistant_messages.extend(router_response.messages)
            for message in router_response.messages:
                await update.message.reply_text(
                    markdownify(message),
                    parse_mode="MarkdownV2"
                )
            
        # Handle delegation if present
        if delegation := router_response.delegation:
            logging.info(f"Delegating to {delegation.delegate_to} with prompt: {delegation.prompt}")
            try:
                delegate_fn = {
                    "claude": get_claude_response,
                    "online": get_online_model_response,
                }.get(delegation.delegate_to)
                if delegate_fn:
                    delegate_response = delegate_fn(delegation.prompt)
                    if isinstance(delegate_response, Exception):
                        logging.error(f"Delegation error: {str(delegate_response)}")
                        await update.message.reply_text(
                            "I'm having trouble getting a response. Please try again."
                        )
                        return
                    assistant_messages.append(delegate_response)
                    await update.message.reply_text(
                        markdownify(delegate_response),
                        parse_mode="MarkdownV2"
                    )
            except Exception as e:
                logging.error(f"Delegation error: {str(e)}")
                await update.message.reply_text(
                    "I'm having trouble processing your request. Please try again."
                )
                return

        # Update conversation memory
        if assistant_messages:
            try:
                new_memory = get_new_bot_memory(
                    existing_memory_data,
                    user_message.content,
                    assistant_messages,
                )
                if isinstance(new_memory, Exception):
                    logging.error(f"Memory error: {str(new_memory)}")
                    return
                    
                memory_dict[chat_id] = MemoryState(
                    memory_content=new_memory,
                    created_at=datetime.now(timezone.utc)
                ).model_dump()  # Convert to dict for storage
            except Exception as e:
                logging.error(f"Error storing memory: {str(e)}")
                # Continue execution even if memory storage fails
                
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        await update.message.reply_text(
            "I apologize, but I encountered an error. Please try again later."
        )


if __name__ == "__main__":
    load_dotenv()
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)