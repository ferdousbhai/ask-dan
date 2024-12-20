import os
import logging
from datetime import datetime, timezone
from pydantic import BaseModel
from telegram import Message
from google import genai
from google.genai import types
from src.helpers.turn_off_safety import turn_off_safety

logging.basicConfig(level=logging.INFO)


#TODO
# Memory objects should be pulled out from a store
# Memory items should be stored back into the store after they are used, sometimes merged, updated, or discarded


MEMORY_SYSTEM_INSTRUCTION = """
    Act as a Telegram bot named Dan's memory system. Track and maintain important information about the user and the chat room.
    
    Tasks:
    1. Preserve ALL user information (preferences, facts, characteristics)
    2. Update previous information when new details are revealed
    3. Consider the temporal context of memories when deciding what to keep or update
    4. When you see conflicting information, keep the most recent version
    
    Your response should be a JSON object with two arrays:
    - chat_memory: array of strings about the conversation
    - user_memory: array of strings about the user
    
    Example format:
    {
        "chat_memory": [
            "User mentioned they like pizza",
        ],
        "user_memory": [
            "User likes pizza",
            "User is friendly"
        ]
    }
    
    Note: You will receive memories with timestamps, but your output should be clean strings without timestamps.
    The system will handle adding timestamps to new or updated memories.
    """


class StoredMemoryItem(BaseModel):
    chat_id: int
    user_id: int
    content: str
    updated_at: datetime

class MemoryStateInput(BaseModel):
    chat_memory: list[StoredMemoryItem]
    user_memory: list[StoredMemoryItem]

class MemoryStateOutput(BaseModel):
    chat_memory: list[str]
    user_memory: list[str]

async def update_bot_memory(
    memory_data: MemoryStateInput | None,
    user_message: Message,
    assistant_response: str,
    model_name: str = os.getenv("MEMORY_MODEL"),
    temperature: float = 0.3,
    api_key: str = os.getenv("GOOGLE_API_KEY")
) -> str | Exception:
    """Maintains a flowing record of the conversation, acting as the bot's memory."""
    try:
        client = genai.Client(api_key=api_key)
        
        current_time = datetime.now(timezone.utc)
        memory_state = "No previous memory" if memory_data is None else memory_data.model_dump_json()
        
        prompt = f"""
        Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M')}
        
        IMPORTANT: Review and incorporate ALL previous memories below:
        Previous Memory State: {memory_state}
        
        Consider this new interaction and merge it with the existing memories:
        User: {user_message.text}
        Assistant: {assistant_response}
        
        Remember to:
        1. Keep ALL relevant information from previous memories
        2. Add new information from this interaction
        3. Update any conflicting information with the newest version
        4. Merge similar or related memories when appropriate
        """

        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=MEMORY_SYSTEM_INSTRUCTION,
                temperature=temperature,
                max_output_tokens=8192,
                safety_settings=turn_off_safety(),
                response_mime_type= 'application/json',
                response_schema= MemoryStateOutput,
            )
        )
        return response.text
            
    except Exception as e:
        logging.exception("Error generating conversation context")
        return e


async def test_memory():
    """Test function to verify memory functionality"""
    from telegram import User, Chat
    
    # Create a mock Message object
    mock_message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="Test User"),
        text="Hi, I like pizza and cats!"
    )
    
    # Test memory update with no previous memory
    return await update_bot_memory(
        memory_data=None,
        user_message=mock_message,
        assistant_response="Hello! I'll remember that you like pizza and cats."
    )

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    import asyncio
    new_memory = asyncio.run(test_memory())
    print(new_memory)