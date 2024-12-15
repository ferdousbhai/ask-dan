import os
import logging
from datetime import datetime, timezone
from pydantic import BaseModel
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Message

class MemoryState(BaseModel):
    memory_content: str
    created_at: datetime

# Configure Gemini model
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Consolidate safety settings and model configuration
MODEL_CONFIG = {
    "model_name": "gemini-2.0-flash-exp",
    "safety_settings": {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
    "generation_config": genai.types.GenerationConfig(
        max_output_tokens=800,
        temperature=2.0,
    )
}

model = genai.GenerativeModel(MODEL_CONFIG["model_name"])

def create_prompt(message: Message, memory_data: MemoryState | None = None) -> str:
    """Create a prompt with optional memory context and metadata."""
    metadata = {
        "user": f"{message.from_user.first_name} {message.from_user.last_name or ''}" if message.from_user else "",
        "chat_type": message.chat.type,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
    }
    if message.reply_to_message:
        metadata["reply_to"] = message.reply_to_message.to_dict()

    parts = [
        "You are a helpful and knowledgeable AI assistant deployed as a Telegram bot. Be direct, clear, and use markdown formatting.",
    ]
    
    if memory_data:
        parts.append(f"Previous context: {memory_data.memory_content}")
        
    parts.append(f"Context: {metadata}")
    parts.append(message.text or message.caption or "")
    
    return "\n\n".join(parts)

async def get_model_response(message: Message, memory_data: MemoryState | None) -> str | Exception:
    """Get response from Gemini model."""
    try:
        prompt = create_prompt(message, memory_data)
        result = await model.generate_content_async(
            prompt,
            safety_settings=MODEL_CONFIG["safety_settings"],
            generation_config=MODEL_CONFIG["generation_config"]
        )
        return result.text
    except Exception as e:
        logging.exception("Error in Gemini API call")
        return e

async def get_new_bot_memory(
    memory_data: MemoryState | None,
    message: Message,
    assistant_response: str,
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
        f"User: {message.text}\n"
        f"Assistant: {assistant_response}\n\n"
        "Provide an updated memory state that:\n"
        "1. Maintains important user information learned so far\n"
        "2. Updates any contradicting information with latest revelations\n"
        "3. Uses UTC timestamps (YYYY-MM-DD HH:MM) for all information\n"
        "4. Compresses older parts while keeping key points\n"
        "Format: Start with 'User Information:' (if any), then 'Previous discussions:' (if any), followed by 'Current discussion:'"
    )
    try:
        result = await model.generate_content_async(prompt, safety_settings=MODEL_CONFIG["safety_settings"])
        return result.text
    except Exception as e:
        logging.exception("Error generating conversation context")
        return e

