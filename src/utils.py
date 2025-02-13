import asyncio
from telegram import Chat as TelegramChat
from telegram.constants import ChatAction

async def show_typing_indicator(chat: TelegramChat, stop_event: asyncio.Event) -> None:
    """Show and maintain a typing indicator until the stop event is set."""
    while not stop_event.is_set():
        await chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(5)