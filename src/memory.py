from datetime import datetime, timezone
import logging
from pydantic import BaseModel

from src.llm_config import get_model, safety_settings

class MemoryState(BaseModel):
    memory_content: str
    created_at: datetime

def get_new_bot_memory(
    memory_data: MemoryState | None,
    user_message: str,
    assistant_responses: list[str],
    model_name: str = "gemini-1.5-flash-latest",
) -> str | Exception:
    """Maintains a flowing record of the conversation, acting as the bot's memory."""
    current_time = datetime.now(timezone.utc)

    memory_context = (
        f"Existing memory as of {memory_data.created_at}: {memory_data.memory_content}\n\n"
        if memory_data
        else ""
    )

    prompt = (
        "Act as a bot named Dan's memory system. Track and maintain important information about the user "
        "and the conversation flow, with precise temporal awareness. Your task is to:\n"
        "1. Preserve ALL user information (preferences, facts, characteristics, etc.)\n"
        "2. When new user information is revealed, update previous information while noting the change\n"
        "3. Track time using UTC timestamps:\n"
        "   - Add a UTC timestamp (YYYY-MM-DD HH:MM) for each piece of information\n"
        "   - For new information, use the current timestamp\n"
        "   - Keep existing timestamps for unchanged information\n"
        "4. For topic changes:\n"
        "   - Keep a brief summary of previous topics under 'Previous discussions:'\n"
        "   - Start 'Current discussion:' for the new topic\n\n"
        f"Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"{memory_context}"
        f"New interaction:\n"
        f"User: {user_message}\n"
        f"Assistant: {' '.join(assistant_responses)}\n\n"
        "Provide an updated memory state that:\n"
        "1. Maintains important user information learned so far\n"
        "2. Updates any contradicting information with latest revelations\n"
        "3. Uses UTC timestamps (YYYY-MM-DD HH:MM) for all information\n"
        "4. Compresses older parts while keeping key points\n"
        "Format: Start with 'User Information:' (if any), then 'Previous discussions:' (if any), followed by 'Current discussion:'"
    )
    try:
        model = get_model(model_name)
        result = model.generate_content(prompt, safety_settings=safety_settings)
        return result.text
    except Exception as e:
        logging.exception("Error generating conversation context")
        return e
