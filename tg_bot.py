import os
from modal import App, Image, Dict, Secret, web_endpoint
from pydantic import BaseModel, Field
from fastapi import Request
import logging
from datetime import datetime, timezone

from utils.markdown_v2_formatter import convert_to_markdown_v2
from system_prompt import get_system_prompt

logging.basicConfig(level=logging.INFO)


app = App("ask-dan-telegram-bot")

telegram_image = Image.debian_slim().pip_install("python-telegram-bot")
llm_image = Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade fastapi pydantic openai instructor"]
)

conversation_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)


class Output(BaseModel):
    thoughts: str | None = Field(
        description="Assistant's thoughts about the user query. If the query is simple, assistant can skip this step. Assistant is encouraged to think deeply about the query and why the user might be asking that, and ask follow-up questions."
    )
    text_messages: list[str] | None = Field(
        description="The responses to the user. It can be skipped if the assistant believes that the user has not completed the query yet and is still in the process of communicating more information, as the assistant waits for the user to finish the query."
    )
    updated_conversation_context: str = Field(
        description="A summary of the current conversation including the user's message and the assistant's response for the last few turns. Please make sure to include all the relevant details of the current conversation so that it can be used as a context by the assistant for continuing this conversation. In case the user switches topic, reset the context for the new topic. In case a long time has passed since the last assistant message, it might be time to start a new topic."
    )


@app.function(image=llm_image, secrets=[Secret.from_name("openai")])
async def get_llm_response(
    chat_id,
    message,
    context: str | None = None,
    last_assistance_response: list[str] | None = None,
    created_at: int | None = None,
    model="gpt-4o",
    temperature=0.8,
) -> tuple[list[str], str]:
    import openai
    import instructor

    client = instructor.from_openai(openai.AsyncOpenAI())

    messages = [
        {"role": "system", "content": get_system_prompt(message, context, created_at)},
        *[
            {"role": "assistant", "content": response}
            for response in (last_assistance_response or [])
        ],
        {"role": "user", "content": message["content"]},
    ]

    response = await client.chat.completions.create(
        model=model, response_model=Output, messages=messages, temperature=temperature
    )
    logging.info(f"LLM response: {response}")
    return (response.text_messages, response.updated_conversation_context)


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
    image=telegram_image,
    secrets=[Secret.from_name("telegram")],
)
async def process_received_message(message):
    from telegram import Bot
    from telegram.constants import ChatAction

    chat_id = message["metadata"]["chat"]["id"]
    bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    context, last_assistance_response, created_at = get_conversation_data(chat_id)
    text_messages, updated_conversation_context = get_llm_response.remote(
        chat_id, message, context, last_assistance_response, created_at
    )

    save_conversation_data(chat_id, text_messages, updated_conversation_context)

    if text_messages:
        for text in text_messages:
            await bot.send_message(
                text=convert_to_markdown_v2(text),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )


def get_conversation_data(chat_id):
    try:
        conversation_data = conversation_dict[chat_id]
        context = conversation_data.get("context")
        last_assistance_response = conversation_data.get("assistance_response")
        created_at = conversation_data.get("created_at")
        logging.info(f"Got conversation data from dict for chat_id: {chat_id}")
    except KeyError:
        context = None
        last_assistance_response = None
        created_at = None
    return context, last_assistance_response, created_at


def save_conversation_data(chat_id, text_messages, updated_conversation_context):
    conversation_dict[chat_id] = {
        "assistance_response": text_messages,
        "context": updated_conversation_context,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
    }

    logging.info("Stored updated context and assistance response to dict.")


@app.local_entrypoint()
async def test_llm():
    output = get_llm_response.remote(
        chat_id=123, message={"role": "user", "content": "Hello"}
    )
    print(output)
