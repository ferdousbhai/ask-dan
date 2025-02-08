import asyncio
import base64
from telegram import Chat, Message as TelegramMessage
from telegram.constants import ChatAction

async def show_typing_indicator(chat: Chat, stop_event: asyncio.Event) -> None:
    """Show and maintain a typing indicator until the stop event is set."""
    while not stop_event.is_set():
        await chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(4)

async def create_user_message(telegram_message: TelegramMessage) -> dict:
    """Create a complete user message from a Telegram message."""
    content_blocks = []

    if telegram_message.photo:
        photo = telegram_message.photo[-1]
        image_bytes = await (await photo.get_file()).download_as_bytearray()
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode('utf-8'),
            }
        })

    if message_text := telegram_message.text or telegram_message.caption:
        content_blocks.append({
            "type": "text",
            "text": message_text
        })

    return {"role": "user", "content": content_blocks}