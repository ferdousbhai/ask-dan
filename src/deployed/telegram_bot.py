import logging
import os
import json
from datetime import datetime, timezone
from typing import TypedDict, Literal

from fastapi import Request
from modal import App, Image, Function, Secret, web_endpoint

from src.core.conversation import get_conversation_data, save_conversation_data
from src.utils.markdown_v2 import convert_to_markdown_v2
from src.prompts.templates import create_system_message

logging.basicConfig(level=logging.INFO)


app = App("ask-dan-telegram-bot")

image = Image.debian_slim(python_version="3.12").pip_install(
    "google-generativeai", "python-telegram-bot"
)

get_online_model_response = Function.lookup("ask-llm", "get_online_model_response")
get_claude_response = Function.lookup("ask-llm", "get_claude_response")


class Delegation(TypedDict):
    delegate_to: Literal["claude", "online"]
    prompt: str


class LLMResponse(TypedDict, total=False):
    messages: list[str]
    delegation: Delegation


class Message(TypedDict):
    id: int
    role: Literal["user", "assistant"]
    content: str
    metadata: dict
    created_at: int


def get_llm_response(
    message: Message,
    conversation_summary: str | None = None,
    model_name: str = "gemini-1.5-flash-latest",
) -> LLMResponse | Exception:
    """
    Get response from Gemini model with delegation capability.
    Returns a dict with optional immediate messages, optional delegation info.
    """
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY: HarmBlockThreshold.BLOCK_NONE,
    }

    kwargs = {
        "metadata": {
            "user": f"{message['metadata']['from']['first_name']} {message['metadata']['from']['last_name']}",
            "chat_type": message["metadata"]["chat"]["type"],
            "current_time": datetime.now(timezone.utc).isoformat(),
            **(
                {
                    "reply_context": {
                        "text": reply_to.get("text"),
                        "from": reply_to.get("from"),
                    }
                }
                if (reply_to := message["metadata"].get("reply_to"))
                else {}
            ),
        },
    }

    system_message = create_system_message(
        "router", conversation_summary or "", **kwargs
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


def get_conversation_context(
    user_message: str,
    assistant_responses: list[str],
    current_context: str | None = None,
    model_name: str = "gemini-1.5-flash-latest",
) -> str | Exception:
    """
    Maintains a flowing record of the conversation, tracking the current topic and discussion.
    If the user changes topic, starts fresh while preserving a brief summary of previous topics.
    Long conversations may be naturally compressed while keeping key points.
    Returns the updated conversation context as a string.
    """
    import google.generativeai as genai

    prompt = (
        "Track this conversation's flow, maintaining context and key points. "
        "If the user changes topic:\n"
        "1. Preserve a one-line summary of the previous topic(s) as 'Previous discussions:'\n"
        "2. Start a new section with 'Current discussion:' for the new topic\n\n"
        f"Current conversation context: {current_context or 'No previous conversation.'}\n\n"
        f"New interaction:\n"
        f"User: {user_message}\n"
        f"Assistant: {' '.join(assistant_responses)}\n\n"
        "Provide an updated conversation context that:\n"
        "1. Maintains brief summaries of previous topics if this is a topic change\n"
        "2. Clearly separates current discussion from previous topics\n"
        "3. Preserves important details of the current discussion\n"
        "4. Compresses older parts while keeping key points\n"
        "Format: Start with 'Previous discussions:' (if any), followed by 'Current discussion:'"
    )

    try:
        model = genai.GenerativeModel(model_name)
        result = model.generate_content(prompt)
        return result.text

    except Exception as e:
        logging.exception("Error generating conversation context")
        return e


@app.function(
    image=image,
    secrets=[Secret.from_name("google-genai"), Secret.from_name("telegram")],
)
async def process_received_message(message: Message):
    from telegram import Bot
    from telegram.constants import ChatAction

    chat_id = message["metadata"]["chat"]["id"]
    user = f"{message['metadata']['from']['first_name']} {message['metadata']['from'].get('last_name', '')}"
    logging.info("Processing message from %s: %.100s...", user, message["content"])

    bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])

    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        conv_data = get_conversation_data(chat_id)

        router_response = get_llm_response(message, conv_data.conversation_summary)
        logging.info(
            "Router response: messages=%s, delegation=%s",
            router_response.get("messages", []),
            router_response.get("delegation"),
        )

        assistant_message_contents = router_response.get("messages", [])
        for msg in assistant_message_contents:
            await bot.send_message(
                text=convert_to_markdown_v2(msg),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )

        if delegation := router_response.get("delegation"):
            logging.info("Delegating to %s", delegation["delegate_to"])
            delegate_fn = {
                "claude": get_claude_response,
                "online": get_online_model_response,
            }.get(delegation["delegate_to"])

            if delegate_fn:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                try:
                    response = await delegate_fn.remote(
                        conv_data.conversation_summary,
                        delegation["prompt"],
                    )
                    await bot.send_message(
                        text=convert_to_markdown_v2(response),
                        chat_id=chat_id,
                        parse_mode="MarkdownV2",
                    )
                    assistant_message_contents.append(response)
                except Exception as e:
                    logging.error("Delegation error: %s", str(e))
                    await bot.send_message(
                        text="I apologize, but I encountered an error while delegating the question.",
                        chat_id=chat_id,
                    )

        if assistant_message_contents:
            context_result = get_conversation_context(
                message["content"],
                assistant_message_contents,
                conv_data.conversation_summary,
            )
            updated_context = (
                context_result
                if not isinstance(context_result, Exception)
                else conv_data.conversation_summary
            )
            logging.info("Updated conversation context: %s", updated_context)

            save_conversation_data(
                chat_id,
                updated_context,
            )

    except Exception as e:
        logging.error("Error processing message: %s", str(e))
        await bot.send_message(
            text="I apologize, but I encountered an error. Please try again later.",
            chat_id=chat_id,
        )


@app.function()
@web_endpoint(method="POST")
async def webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"status": "ok"}

    tg_message = data["message"]

    if tg_message and tg_message.get("text"):
        message = Message(
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

        process_received_message.spawn(message)

    return {"status": "ok"}
