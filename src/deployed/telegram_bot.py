import logging
import os
import json
from datetime import datetime, timezone
from typing import TypedDict, Literal

from fastapi import Request
from modal import App, Image, Function, Dict, Secret, web_endpoint

from src.utils.markdown_v2 import convert_to_markdown_v2
from src.prompts.templates import create_system_message


logging.basicConfig(level=logging.INFO)


app = App("ask-dan-telegram-bot")

image = Image.debian_slim(python_version="3.12").pip_install(
    "google-generativeai", "python-telegram-bot"
)

get_online_model_response = Function.lookup("ask-llm", "get_online_model_response")
get_claude_response = Function.lookup("ask-llm", "get_claude_response")

chat_memory = Dict.from_name("dan-conversation-state", create_if_missing=True)

class MemoryState(TypedDict, total=False):
    memory_content: str
    created_at: int

class Message(TypedDict):
    id: int
    role: Literal["user", "assistant"]
    content: str
    metadata: dict
    created_at: int

class Delegation(TypedDict):
    delegate_to: Literal["claude", "online"]
    prompt: str

class LLMResponse(TypedDict, total=False):
    messages: list[str]
    delegation: Delegation


def get_llm_response(
    message: Message,
    memory_content: str | None = None,
    model_name: str = "gemini-1.5-flash-latest",
) -> LLMResponse | Exception:
    """
    Get response from Gemini model with delegation capability.
    """
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

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

    system_message = create_system_message(
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
    """
    Maintains a flowing record of the conversation, acting as the bot's memory.
    """
    import google.generativeai as genai
    from datetime import datetime, timezone

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


def create_message_from_telegram(tg_message: dict) -> Message | None:
    """Creates a Message object from a Telegram message dictionary."""
    """Only supports text messages for now"""

    if tg_message.get("text"):
        return Message(
            id=tg_message.get("message_id"),
            role="user",
            content=tg_message.get("text"),
            metadata={
                "from": tg_message.get("from"),
                "chat": tg_message.get("chat"),
                "reply_to": tg_message.get("reply_to_message"),
            },
            created_at=tg_message.get("date"),
        )


@app.function(
    image=image,
    secrets=[Secret.from_name("google-genai"), Secret.from_name("telegram")],
)
async def process_received_message(tg_message: dict) -> None:
    from telegram import Bot
    from telegram.constants import ChatAction

    message = create_message_from_telegram(tg_message)
    if not message:
        return 

    chat_id = message["metadata"]["chat"]["id"]
    bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])

    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        memory_state = get_memory_state(chat_id)
        
        router_response = get_llm_response(
            message, 
            memory_state.get("memory_content", "")
        )
        if isinstance(router_response, Exception):
            raise router_response
            
        assistant_messages = router_response.get("messages", [])
        
        # Send initial messages directly
        for msg in assistant_messages:
            await bot.send_message(
                chat_id=chat_id,
                text=convert_to_markdown_v2(msg),
                parse_mode="MarkdownV2"
            )
            
        # Handle delegation if present
        if delegation := router_response.get("delegation"):
            delegate_fn = {
                "claude": get_claude_response,
                "online": get_online_model_response,
            }.get(delegation["delegate_to"])
            
            if delegate_fn:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                response = delegate_fn.remote(
                    memory_state.get("memory_content", ""),
                    delegation["prompt"],
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=convert_to_markdown_v2(response),
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
        await bot.send_message(
            chat_id=chat_id,
            text="I apologize, but I encountered an error. Please try again later."
        )


@app.function()
@web_endpoint(method="POST")
async def webhook(request: Request) -> dict[str, str]:
    data = await request.json()
    if tg_message := data.get("message"):
        process_received_message.spawn(tg_message)
    return {"status": "ok"}


def get_memory_state(chat_id: int) -> MemoryState:
    try:
        data = chat_memory[chat_id]
        return MemoryState(
            memory_content=data.get("memory_content", ""),
            created_at=data.get("created_at", int(datetime.now(timezone.utc).timestamp()))
        )
    except KeyError:
        return MemoryState(
            memory_content="",
            created_at=int(datetime.now(timezone.utc).timestamp())
        )


def save_memory_state(chat_id: int, new_content: str) -> None:
    try:
        chat_memory[chat_id] = {
            "memory_content": new_content,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
    except Exception as e:
        logging.exception("Error saving memory state")
        raise e
