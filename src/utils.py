import asyncio
from telegram import Chat
from telegram.constants import ChatAction

async def show_typing_indicator(chat: Chat, stop_event: asyncio.Event) -> None:
    """Show and maintain a typing indicator until the stop event is set."""
    while not stop_event.is_set():
        await chat.send_chat_action(ChatAction.TYPING)
        await asyncio.sleep(4)


def split_long_message(message: str, max_length: int = 4096) -> list[str]:
    """
    Split a message into chunks if it exceeds Telegram's message length limit.
    Attempts to split at paragraph boundaries first, then at sentence boundaries,
    and finally at word boundaries if necessary.

    Args:
        message: The message text to split
        max_length: Maximum length of each chunk (Telegram's limit is 4096 characters)

    Returns:
        A list containing message chunks. If the message is within limits, returns a single-item list.
    """
    if len(message) <= max_length:
        return [message]

    chunks = []
    current_chunk = ""

    # First try to split at paragraph boundaries
    paragraphs = [p.strip() for p in message.split('\n\n') if p.strip()]

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 2 <= max_length:
            current_chunk = f"{current_chunk}\n\n{paragraph}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)

            # If a single paragraph is too long, split it at sentence boundaries
            if len(paragraph) > max_length:
                sentences = [s.strip() for s in paragraph.replace('\n', ' ').split('. ')]
                current_chunk = ""

                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 2 <= max_length:
                        current_chunk = f"{current_chunk}. {sentence}".strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)

                        # If a single sentence is too long, split at word boundaries
                        if len(sentence) > max_length:
                            words = sentence.split()
                            current_chunk = ""

                            for word in words:
                                if len(current_chunk) + len(word) + 1 <= max_length:
                                    current_chunk = f"{current_chunk} {word}".strip()
                                else:
                                    chunks.append(current_chunk)
                                    current_chunk = word
                        else:
                            current_chunk = sentence
            else:
                current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk)

    return chunks