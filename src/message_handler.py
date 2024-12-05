import logging
from datetime import datetime, timezone
from typing import TypedDict, Literal

class MemoryState(TypedDict, total=False):
    memory_content: str
    created_at: int

class Message(TypedDict):
    id: int
    role: Literal["user", "assistant"]
    content: str
    metadata: dict
    created_at: int

# In-memory storage (replace with Redis or DB in production)
chat_memory = {}

def create_message_from_telegram(tg_message: dict) -> Message | None:
    """Creates a Message object from a Telegram message dictionary."""
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

def get_memory_state(chat_id: int) -> MemoryState:
    """Get memory state for a chat."""
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
    """Save memory state for a chat."""
    try:
        chat_memory[chat_id] = {
            "memory_content": new_content,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
    except Exception as e:
        logging.exception("Error saving memory state")
        raise e 