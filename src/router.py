import logging
import os
import json
from datetime import datetime, timezone
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from src.prompt import create_system_message_content
from src.message_handler import Message, LLMResponse

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

def get_llm_response(
    message: Message,
    memory_content: str | None = None,
    model_name: str = "gemini-1.5-flash-latest",
) -> LLMResponse | Exception:
    """Get response from Gemini model with delegation capability."""

    kwargs = {
        "metadata": {
            "user": f"{message['metadata']['from']['first_name']} {message['metadata']['from']['last_name']}",
            "chat_type": message["metadata"]["chat"]["type"],
            "current_time": datetime.now(timezone.utc).isoformat(),
        }
    }

    if reply_to := message["metadata"].get("reply_to"):
        kwargs["metadata"]["reply_context"] = {
            "text": reply_to.get("text"),
            "from": reply_to.get("from"),
        }

    system_message = create_system_message_content(
        "router", memory_content or "", **kwargs
    )

    try:
        model = genai.GenerativeModel(model_name)
        result = model.generate_content(
            f"{system_message}\n\n{message['content']}",
            safety_settings=safety_settings,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "messages": {"type": "array", "items": {"type": "string"}},
                        "delegation": {
                            "type": "object",
                            "properties": {
                                "delegate_to": {
                                    "type": "string",
                                    "enum": ["claude", "online"],
                                },
                                "prompt": {"type": "string"},
                            },
                            "required": ["delegate_to", "prompt"],
                        },
                    },
                },
            ),
        )

        response_data = json.loads(result.parts[0].text)
        return LLMResponse(**{k: v for k, v in response_data.items() if v is not None})

    except Exception as e:
        logging.exception("Error in Gemini API call or parsing response")
        return e

def update_bot_memory(
    user_message: str,
    assistant_responses: list[str],
    current_context: str | None = None,
    model_name: str = "gemini-1.5-flash-latest",
) -> str | Exception:
    """Maintains a flowing record of the conversation, acting as the bot's memory."""
    current_time = datetime.now(timezone.utc)
    
    prompt = (
        "Act as a bot named Dan's memory system. Track and maintain important information about the user "
        "and the conversation flow, including temporal awareness. Your task is to:\n"
        "1. Preserve ALL user information (preferences, facts, characteristics, etc.)\n"
        "2. When new user information is revealed, update previous information while noting the change\n"
        "3. Track time in a natural way:\n"
        "   - Use relative time references (e.g., 'earlier today', 'yesterday', 'last week')\n"
        "   - Only note specific dates for truly important events\n"
        "   - Avoid detailed timestamps unless absolutely necessary\n"
        "4. For topic changes:\n"
        "   - Keep a brief summary of previous topics under 'Previous discussions:'\n"
        "   - Start 'Current discussion:' for the new topic\n\n"
        f"Current UTC time: {current_time.isoformat()}\n"
        f"Current memory state: {current_context or 'No previous conversation.'}\n\n"
        f"New interaction:\n"
        f"User: {user_message}\n"
        f"Assistant: {' '.join(assistant_responses)}\n\n"
        "Provide an updated memory state that:\n"
        "1. Maintains important user information learned so far\n"
        "2. Updates any contradicting information with latest revelations\n"
        "3. Keeps track of discussion flow with natural time references\n"
        "4. Compresses older parts while keeping key points\n"
        "Format: Start with 'Last Updated: <natural time>', then 'User Information:' (if any), "
        "then 'Previous discussions:' (if any), followed by 'Current discussion:'"
    )

    try:
        model = genai.GenerativeModel(model_name)
        result = model.generate_content(prompt)
        return result.text

    except Exception as e:
        logging.exception("Error generating conversation context")
        return e
