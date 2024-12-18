from datetime import datetime, timezone
import logging
import os
from pydantic import BaseModel

from telegram import Message
from google import genai
from google.genai import types


client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


class MemoryItem(BaseModel):
    content: str
    updated_at: datetime

class MemoryState(BaseModel):
    chat_memory: list[MemoryItem]
    user_memory: list[MemoryItem]

async def update_bot_memory(
    memory_data: MemoryState | None,
    user_message: Message,
    assistant_response: str,
    model_name: str = os.getenv("MEMORY_MODEL"),
    temperature = 0.3
) -> str | Exception:
    """Maintains a flowing record of the conversation, acting as the bot's memory."""
    current_time = datetime.now(timezone.utc)
        
    system_instruction = """
    Act as a Telegram bot named Dan's memory system. Track and maintain important information about the user and the chat room, with precise temporal awareness.
    
    Tasks:
    1. Preserve ALL user information (preferences, facts, characteristics)
    2. Update previous information when new details are revealed
    3. Track time using UTC timestamps (YYYY-MM-DD HH:MM)
    
    Provide an updated memory state that maintains and updates important user information with timestamps.
    """

    memory_state = "No previous memory" if memory_data is None else memory_data.model_dump_json()

    prompt = f"""
    Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M')}
    Previous Memory State: {memory_state}
    New interaction:
    User: {user_message.text}
    Assistant: {assistant_response}
    """

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=temperature)
        )
        return response.text
            
    except Exception as e:
        logging.exception("Error generating conversation context")
        return e