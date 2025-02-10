import asyncio
import logging
import os
import re
from google import genai
from google.genai import types
from google.genai.chats import AsyncChat
from telegram import Update
from telegram.ext import ContextTypes
from telegramify_markdown import markdownify
from src.safety import safety_settings
from src.tools.schema import tools
from src.tools.url import scrape_url
from src.tools.research import get_online_research
from src.system_prompt import get_system_prompt
from src.utils import show_typing_indicator, split_response_into_paragraphs

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# In-memory chat history storage
chat_by_id: dict[int, AsyncChat] = {}

def create_chat(chat_id: int, system_instruction: str | None = None, temperature: float = 1) -> AsyncChat:
    chat: AsyncChat = client.aio.chats.create(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            safety_settings=safety_settings,
            tools=tools
        )
    )
    chat_by_id[chat_id] = chat
    return chat

async def handle_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages from users."""
    message = update.message
    if not message or not (message.text or message.photo): #TODO: Add support for photos
        return

    chat_id = update.effective_chat.id
    chat: AsyncChat = chat_by_id.get(chat_id) or create_chat(chat_id, get_system_prompt(message))
    typing_task = asyncio.create_task(show_typing_indicator(update.effective_chat, stop_typing_event := asyncio.Event()))

    try:
        # Send initial message to the model
        response = await chat.send_message(update.message.text)

        # Process function calls until none remain
        while response.function_calls:
            function_call = response.function_calls[0]
            function_name = function_call.name
            function_args = function_call.args

            try:
                # Execute the appropriate function
                if function_name == "get_online_research":
                    result = await get_online_research(**function_args)
                elif function_name == "scrape_url":
                    result = await scrape_url(**function_args)
                elif function_name == "start_a_new_conversation":
                    chat = create_chat(chat_id, get_system_prompt(message))
                    result = "Conversation reset successfully"
                else:
                    raise ValueError(f"Unknown function: {function_name}")

                # Format the function response according to SDK specifications
                function_response = {
                    "name": function_name,
                    "response": {
                        "result": result if not isinstance(result, Exception) else None,
                        "error": str(result) if isinstance(result, Exception) else None
                    }
                }

                # Send function response back to model
                response = await chat.send_message(
                    types.Part.from_function_response(**function_response)
                )

            except Exception as e:
                logger.error(f"Error executing function {function_name}: {str(e)}", exc_info=True)
                # Send error response back to model
                response = await chat.send_message(
                    types.Part.from_function_response(
                        name=function_name,
                        response={"error": str(e)}
                    )
                )

        # Process final text response
        logger.info(f"Model response text: {response.text}")
        response_text = re.sub(r'<think>[\s\S]*?</think>', '', response.text)

        # Split and send paragraphs
        paragraphs = split_response_into_paragraphs(response_text)
        for paragraph in paragraphs:
            if paragraph:
                await update.message.reply_text(
                    markdownify(paragraph),
                    parse_mode="MarkdownV2"
                )

    except Exception as e:
        logger.error(f"Error in message handling: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "I apologize, but I encountered an error processing your request. "
            "Please try again later or contact @ferdousbhai for support."
        )
    finally:
        stop_typing_event.set()
        await typing_task