import os
import logging
from google import genai
from google.genai import types
from google.genai.chats import AsyncChat
from .functions.schema import tools
from .safety_settings import safety_settings

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# In-memory chat history storage
chat_by_id: dict[int, AsyncChat] = {}

def get_chat(chat_id: int) -> AsyncChat:
    return chat_by_id.get(chat_id)

def create_chat(chat_id: int, system_instruction: str, temperature: float = 1.2, safety_settings: list[types.SafetySetting] = safety_settings, tools: list[types.Tool] = tools) -> AsyncChat:
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

def clear_chat(chat_id: int, reason: str | None = None) -> bool:
    if chat_id in chat_by_id:
        if reason:
            logger.warning(f"Clearing chat {chat_id} because: {reason}")
        del chat_by_id[chat_id]
        return True
    return False