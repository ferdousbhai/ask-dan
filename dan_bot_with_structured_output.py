import os
from modal import App, Image, Dict, Secret, web_endpoint
from pydantic import BaseModel, Field
from fastapi import Request
import logging
from datetime import datetime, timezone

from utils.markdown_v2_formatter import convert_to_markdown_v2

logging.basicConfig(level=logging.INFO)


app = App("ask-dan-telegram-bot")


image = Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade fastapi pydantic openai instructor python-telegram-bot"]
)


conversation_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)


class Output(BaseModel):
    thoughts: str | None = Field(
        description="Assistant's thoughts about the user query. Assistant is encouraged to think deeply about the query and why the user might be asking that, and ask follow-up questions. If the query is simple, assistant can skip this step."
    )
    text_messages: list[str] | None = Field(
        description="The responses to the user. It can be skipped if the assistant believes that the user has not completed the query yet and is still in the process of communicating more information, as the assistant waits for the user to finish the query."
    )
    updated_conversation_context: str = Field(
        description="A summary of the current conversation including the user's message and the assistant's response for the last few turns. Please make sure to include all the relevant details of the current conversation so that it can be used as a context by the assistant for continuing this conversation. In case the user switches topic, reset the context for the new topic. In case a long time has passed since the last assistant message, it might be time to start a new topic."
    )


@app.function(keep_warm=1)
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


def save_conversation_data(chat_id, output):
    conversation_dict[chat_id] = {
        "assistance_response": output.text_messages,
        "context": output.updated_conversation_context,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
    }
    logging.info("Stored updated context and assistance response to dict.")


def get_openai_response(
    chat_id,
    message,
    context,
    last_assistance_response,
    created_at,
    model="gpt-4o-mini",
):
    import instructor
    from openai import OpenAI

    client = instructor.from_openai(OpenAI())

    try:
        output = client.chat.completions.create(
            model=model,
            response_model=Output,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Dan, a kind, helpful assistant."
                        f"You are chatting with {message['metadata']['from']['first_name']} {message['metadata']['from']['last_name']} in a {message['metadata']['chat']['type']} chat on telegram."
                        "Keep responses short and concise. If you need to explain something in more detail, you can do so by sending multiple short messages."
                        f"Current date and time is {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
                        f"The last message from the assistant was generated at {datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M:%S')}."
                        if created_at
                        else "" f"<context>{context}</context>"
                        if context
                        else ""
                    ),
                },
                *(
                    [
                        {
                            "role": "assistant",
                            "content": response,
                        }
                        for response in last_assistance_response
                    ]
                    if last_assistance_response
                    else []
                ),
                {"role": "user", "content": message["content"]},
            ],
            temperature=0.8,
        )
        logging.info(f"Output: {output}")
        return output
    except Exception as e:
        logging.error(f"Error getting openai response: {e}")
        return None


@app.function(
    image=image,
    secrets=[Secret.from_name("openai"), Secret.from_name("telegram")],
    keep_warm=1,
)
async def process_received_message(message):
    from telegram import Bot
    from telegram.constants import ChatAction

    chat_id = message["metadata"]["chat"]["id"]

    bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    context, last_assistance_response, created_at = get_conversation_data(chat_id)

    output = get_openai_response(
        chat_id, message, context, last_assistance_response, created_at
    )

    save_conversation_data(chat_id, output)

    if output.text_messages:
        for text in output.text_messages:
            await bot.send_message(
                text=convert_to_markdown_v2(text),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )
