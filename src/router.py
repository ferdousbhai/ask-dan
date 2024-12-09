import logging
import json
from datetime import datetime, timezone

import google.generativeai as genai

from src.prompt import create_system_message_content
from src.message_handler import Message
from src.llm_config import safety_settings, get_model
from src.memory import MemoryState
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)


class DelegationConfig(BaseModel):
    delegate_to: str
    prompt: str

class RouterResponse(BaseModel):
    messages: list[str] | None = None
    delegation: DelegationConfig | None = None

def get_router_response(
    message: Message,
    memory_data: MemoryState,
    model_name: str = "gemini-1.5-flash-latest",
) -> RouterResponse | Exception:
    """Get response from Gemini model with delegation capability."""

    kwargs = {
        "metadata": {
            "user": f"{message.metadata['from']['first_name']} {message.metadata['from']['last_name']}",
            "chat_type": message.metadata["chat"]["type"],
            "current_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        }
    }
    if reply_to := message.metadata.get("reply_to"):
        kwargs["metadata"]["reply_context"] = {
            "text": reply_to.get("text"),
            "from": reply_to.get("from"),
        }

    system_message = create_system_message_content(
        "router", memory_data, **kwargs
    )

    response_schema = {
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
                        }
                    },
                }

    try:
        model = get_model(model_name)
        result = model.generate_content(
            f"{system_message}\n\n{message.content}",
            safety_settings=safety_settings,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        response_data = json.loads(result.parts[0].text)
        return RouterResponse(**response_data)

    except Exception as e:
        logging.exception("Error in Gemini API call or parsing response")
        return e

