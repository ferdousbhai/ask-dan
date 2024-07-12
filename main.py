# use conversation to maintain the state of a conversation in summarized form in a dict. Should keep chat_id, and when starting new conversation, save the summary of the old conversation to a vector DB.
# can process links to youtube videos, images, x.com posts, webpages via action.
# additional actions can be added and should be called with RAG

import os
from modal import App, Image, Dict, Secret, web_endpoint
from fastapi import Request
import logging
from markdown_v2_formatter import convert_to_markdown_v2

logging.basicConfig(level=logging.INFO)


app = App("telegram-bot")


main_image = Image.debian_slim(python_version="3.12").run_commands(
    ["pip install --upgrade fastapi pydantic openai instructor python-telegram-bot"]
)

# reranker_image = Image.debian_slim(python_version="3.12").run_commands(
#     ["pip install cohere"]
# )

conversation_dict = Dict.from_name(
    "telegram-conversation-state", create_if_missing=True
)
# {
#   <chat_id>: {
#     context: str
#   }
# }


@app.function(keep_warm=1)
@web_endpoint(method="POST")
async def webhook(request: Request):
    tg_message = (await request.json())["message"]
    logging.info(f"Received telegram message: {tg_message}")

    # example:
    #   'message_id': 123,
    #   'from': {'id': 284568525, 'is_bot': False, 'first_name': 'Ferdous', 'last_name': '฿hai', 'username': 'ferdousbhai', 'language_code': 'en', 'is_premium': True},
    #   'chat': {'id': 284568525, 'first_name': 'Ferdous', 'last_name': '฿hai', 'username': 'ferdousbhai', 'type': 'private'},
    #   'date': 1719747449,
    #   'text': '...'
    # }
    if tg_message.get("text"):  # Currently only supports text messages
        openai_message = {
            "id": tg_message.get("message_id"),
            "role": "user",
            "content": tg_message.get("text"),
            "metadata": {
                "from": tg_message.get("from"),
                "chat": tg_message.get("chat"),
            },
            "created_at": tg_message.get("date"),
        }
        process_received_message.spawn(openai_message)
    return {"status": "ok"}


@app.function(
    image=main_image,
    secrets=[Secret.from_name("openai"), Secret.from_name("telegram")],
    keep_warm=1,
)
async def process_received_message(message):
    from telegram import Bot
    from telegram.constants import ChatAction
    from pydantic import BaseModel, Field
    from typing import Literal
    import instructor
    from openai import OpenAI
    from datetime import datetime

    client = instructor.from_openai(OpenAI())

    chat_id = message["metadata"]["chat"]["id"]
    context = conversation_dict.get(chat_id).get("context")

    bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])

    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    class Knowledge(BaseModel):
        content: str
        scope: Literal["chat", "global"] = Field(
            description="Whether the knowledge is specific to the current user or global to all users.",
            default="chat",
        )
        timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp()))

    class Output(BaseModel):
        thoughts: str | None = Field(
            description="Assistant's thoughts about the user query. Is there a deeper reason behind the query? Assistant is encouraged to make a hypthesis and ask follow-up questions. If the user query is simple, assistant can skip this step."
        )
        text_messages: list[str] | None = Field(
            description="The generated text responses to the user. It can be skipped if the assistant believes that the user has not completed the query yet and is still in the process of communicating more information, as the assistant waits for the user to finish the query."
        )
        updated_conversation_context: str = Field(
            description="A summary of the current conversation. Please make sure to include all the details of the current conversation so that it can be used as a context by the assistant for continuing this conversation. In case the user switches topic, reset the context for the new topic.",
        )
        # In case the user switches topic, assistant should save the conversation context to memory by calling the `save_conversation` function and reset the context for the new topic."
        lessons: list[Knowledge] | None = Field(
            description="Assistant will remember this for future conversations."
        )

    output = client.chat.completions.create(
        model="gpt-4o",
        response_model=Output,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Dan, a kind, warm, helpful assistant named after the infamous ChatGPT jailbreak attempt Do Anything Now."
                    "Please use one of the tools to respond to user question whenever possible, and mention when none of the resources are sufficient."
                    f"You are chatting with {message['metadata']['from']['first_name']} {message['metadata']['from']['last_name']} in a {message['metadata']['chat']['type']} chat on telegram. You may occassionally refer to the user by their first name."
                    f"The chat id is {chat_id} which you may use for function calls if needed. Do not reveal the chat id to the user."
                    "Keep responses short and concise. If you need to explain something in more detail, you can do so by sending multiple short messages."
                    "You can use Markdown if needed."
                    f"The last message from the user was generated at {datetime.fromtimestamp(message['created_at']).strftime('%Y-%m-%d %H:%M:%S')}."
                    f"Current date and time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    f"<context>{context}</context>"
                    if context
                    else ""
                ),
            },
            {"role": "user", "content": message["content"]},
        ],
        temperature=0.8,
        # tools=[
        #     {"type": "code_interpreter"},
        #     {"type": "search"},
        #     {"type": "function"},
        #     save_conversation(chat_id), search_chat_memory(chat_id), search_global_memory
        # ],
    )
    logging.info(f"Output: {output}")

    if output.text_messages:
        for text in output.text_messages:
            await bot.send_message(
                text=convert_to_markdown_v2(text),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )

    if output.updated_conversation_context:
        conversation_dict[chat_id] = {
            "context": output.updated_conversation_context,
        }

    if output.lessons:
        ...
