from datetime import datetime, timezone
import json
import logging
import os

from pydantic import BaseModel
from modal import App, Image, Dict, Secret, web_endpoint
from fastapi import Request

from utils.markdown_v2_formatter import convert_to_markdown_v2

logging.basicConfig(level=logging.INFO)


class LLMConfig(BaseModel):
    name: str
    provider: str
    base_url: str | None = None


LLM_CLIENTS = {
    "groq": lambda base_url=None: __import__("groq").Groq(),
    "anthropic": lambda base_url=None: __import__("anthropic").Anthropic(),
    "perplexity": lambda base_url: __import__("openai").OpenAI(
        api_key=os.environ["PERPLEXITY_API_KEY"],
        base_url=base_url,
    ),
}

LLM_CONFIGS = {
    "router": LLMConfig(name="llama-3.1-8b-instant", provider="groq"),
    "online": LLMConfig(
        name="llama-3.1-sonar-large-128k-online",
        provider="perplexity",
        base_url="https://api.perplexity.ai",
    ),
    "general": LLMConfig(name="claude-3-5-sonnet-latest", provider="anthropic"),
}

app = App("ask-dan-telegram-bot")

image = Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade fastapi pydantic openai groq anthropic python-telegram-bot"]
)

conversation_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)


class RouterResponse(BaseModel):
    delegate_to: str | None = None
    delegation_reason: str | None = None
    thoughts: str | None = None
    text_messages: list[str] = []
    updated_conversation_context: str


class SystemMessageTemplate(BaseModel):
    base_description: str
    guidelines: list[str]


SYSTEM_TEMPLATES = {
    "router": SystemMessageTemplate(
        base_description=(
            "You are Dan, a kind, helpful assistant whose primary role is to analyze queries "
            "and delegate them to specialized models when appropriate. "
            "Delegate to 'claude' for complex reasoning, analysis, or detailed explanations. "
            "Delegate to 'online' for current events, real-time information, or fact-checking. "
            "Only handle simple, straightforward queries yourself. "
            "Always maintain conversation context for future interactions."
        ),
        guidelines=[
            "You must respond in JSON format with the following fields:",
            "- delegate_to: (optional) Either 'claude' or 'online' if the query should be delegated",
            "- delegation_reason: (optional) Explain why the query is being delegated",
            "- thoughts: (optional) Your reasoning process",
            "- text_messages: Array of strings containing your response",
            "- updated_conversation_context: String summarizing the current conversation state (REQUIRED)",
        ],
    ),
    "claude": SystemMessageTemplate(
        base_description="You are a highly capable AI assistant focused on providing accurate, "
        "thoughtful, and nuanced responses. You excel at complex reasoning, analysis, "
        "and detailed explanations while maintaining a kind and compassionate tone.",
        guidelines=[
            "Provide comprehensive yet concise explanations",
            "Be direct and clear in your responses",
            "Use markdown for formatting",
        ],
    ),
    "online": SystemMessageTemplate(
        base_description="You are an AI assistant with real-time access to online information. "
        "Your responses should be accurate, up-to-date, and well-structured. "
        "Focus on providing factual, verifiable information while maintaining a helpful and engaging tone.",
        guidelines=[
            "Cite sources when appropriate",
            "Acknowledge if information might be time-sensitive",
            "Be clear about any uncertainties",
            "Provide context when necessary",
            "Use markdown for formatting",
        ],
    ),
}


def create_system_message(
    template_key: str, context: str, thoughts: str | None = None, **kwargs
) -> str:
    template = SYSTEM_TEMPLATES[template_key]
    parts = [
        template.base_description,
        "Guidelines:",
        *[f"- {guideline}" for guideline in template.guidelines],
        f"\n<context>{context}</context>",
    ]
    if thoughts:
        parts.append(thoughts)
    if kwargs:
        parts.extend(f"{k}: {v}" for k, v in kwargs.items())
    return "\n".join(parts)


def create_llm_client(config: LLMConfig):
    client_factory = LLM_CLIENTS[config.provider]
    return client_factory(getattr(config, "base_url", None))


@app.function(image=image, secrets=[Secret.from_name("groq")])
def get_llm_response(
    chat_id: int,
    message: dict,
    context: str | None = None,
    last_assistance_response: list[str] | None = None,
    temperature=1,
) -> dict:
    logging.info(f"Processing LLM request for chat_id: {chat_id}")

    try:
        config = LLM_CONFIGS["router"]
        client = create_llm_client(config)

        system_prompt = create_system_message(
            "router",
            context or "",
            metadata={
                "user": f"{message['metadata']['from']['first_name']} {message['metadata']['from']['last_name']}",
                "chat_type": message["metadata"]["chat"]["type"],
                "current_time": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            },
        )

        completion = client.chat.completions.create(
            model=config.name,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                *[
                    {"role": "assistant", "content": response}
                    for response in (last_assistance_response or [])
                ],
                {"role": "user", "content": message["content"]},
            ],
            temperature=temperature,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        # Add a fallback for the response parsing
        try:
            response = RouterResponse(
                **json.loads(completion.choices[0].message.content)
            )
        except Exception as parse_error:
            logging.error(f"Error parsing router response: {parse_error}")
            # Provide default response with required fields
            response = RouterResponse(
                text_messages=[str(completion.choices[0].message.content)],
                updated_conversation_context=context or "",
            )

        if response.delegate_to:
            logging.info(f"Delegating to {response.delegate_to}")
            delegate_fn = {
                "claude": get_claude_response,
                "online": get_online_model_response,
            }.get(response.delegate_to)

            if delegate_fn:
                response.text_messages = delegate_fn.remote(
                    message, context, response.thoughts
                )

        return response.dict()
    except Exception as e:
        logging.error(f"Error in get_llm_response: {str(e)}")
        return RouterResponse(
            text_messages=[
                "I apologize, but I encountered an error. Please try again later."
            ],
            updated_conversation_context=context or "",
        ).dict()


@app.function(image=image, secrets=[Secret.from_name("anthropic")])
def get_claude_response(message, context, thoughts) -> list[str]:
    config = LLM_CONFIGS["general"]
    client = create_llm_client(config)

    system_message = create_system_message("claude", context, thoughts)

    response = client.messages.create(
        model=config.name,
        max_tokens=1024,
        temperature=1,
        system=system_message,
        messages=[{"role": "user", "content": message["content"]}],
    )

    return [response.content[0].text]


@app.function(image=image, secrets=[Secret.from_name("perplexity")])
def get_online_model_response(message, context, thoughts) -> list[str]:
    config = LLM_CONFIGS["online"]
    client = create_llm_client(config)

    system_message = create_system_message("online", context, thoughts)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": message["content"]},
    ]

    response = client.chat.completions.create(
        model=config.name,
        messages=messages,
        temperature=0.7,
        max_tokens=1024,
    )

    return [response.choices[0].message.content]


@app.function()
@web_endpoint(method="POST")
async def webhook(request: Request):
    data = await request.json()
    tg_message = data["message"]
    logging.info(f"Received telegram message: {tg_message}")

    if tg_message and tg_message.get("text"):
        process_received_message.spawn(
            {
                "id": tg_message.get("message_id"),
                "role": "user",
                "content": tg_message.get("text"),
                "metadata": {
                    "from": tg_message.get("from"),
                    "chat": tg_message.get("chat"),
                },
                "created_at": tg_message.get("date"),
            }
        )
    return {"status": "ok"}


@app.function(
    image=image,
    secrets=[Secret.from_name("telegram")],
)
async def process_received_message(message):
    try:
        from telegram import Bot
        from telegram.constants import ChatAction

        chat_id = message["metadata"]["chat"]["id"]
        bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        conv_data = get_conversation_data(chat_id)
        response = get_llm_response.remote(
            chat_id, message, conv_data.context, conv_data.assistance_response
        )

        save_conversation_data(
            chat_id,
            response.get("text_messages", []),
            response.get("updated_conversation_context", ""),
        )

        for text in response.get("text_messages", []):
            await bot.send_message(
                text=convert_to_markdown_v2(text),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])
        await bot.send_message(
            text="I apologize, but I encountered an error. Please try again later.",
            chat_id=message["metadata"]["chat"]["id"],
        )


class ConversationData(BaseModel):
    context: str | None = None
    assistance_response: list[str] = []
    created_at: int | None = None


def get_conversation_data(chat_id: int) -> ConversationData:
    try:
        data = conversation_dict[chat_id]
        return ConversationData(**data)
    except KeyError:
        return ConversationData()


def save_conversation_data(
    chat_id: int, text_messages: list[str], updated_context: str
) -> None:
    conversation_dict[chat_id] = {
        "assistance_response": text_messages,
        "context": updated_context,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
    }


@app.local_entrypoint()
async def test_llm():
    response = get_llm_response.remote(
        chat_id=123,
        message={
            "metadata": {
                "from": {"first_name": "John", "last_name": "Doe"},
                "chat": {"type": "group"},
            },
            "content": "What's new on Hacker News?",
        },
    )
    print(response.get("text_messages"))
