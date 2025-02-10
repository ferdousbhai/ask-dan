import asyncio
from telegram import Chat
from telegram.constants import ChatAction

async def show_typing_indicator(chat: Chat, stop_event: asyncio.Event) -> None:
    """Show and maintain a typing indicator until the stop event is set."""
    while not stop_event.is_set():
        await chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(4)

def split_response_into_paragraphs(response_text: str) -> list[str]:
    """
    Split a markdown response text into paragraphs, ensuring headers stay with their content.

    Args:
        response_text: The markdown formatted text to split

    Returns:
        A list of paragraph strings, with headers combined with their content
    """
    paragraphs = []
    temp_paragraphs = [p.strip() for p in response_text.split('\n\n') if p.strip()]
    i = 0
    while i < len(temp_paragraphs):
        current = temp_paragraphs[i]
        # Check if current paragraph is a header (starts with #)
        if current.lstrip().startswith('#'):
            # Combine header with next paragraph if available
            if i + 1 < len(temp_paragraphs):
                paragraphs.append(f"{current}\n\n{temp_paragraphs[i + 1]}")
                i += 2
            else:
                paragraphs.append(current)
                i += 1
        else:
            paragraphs.append(current)
            i += 1
    return paragraphs