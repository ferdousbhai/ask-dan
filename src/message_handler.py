from typing import Literal
from pydantic import BaseModel

class Message(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    metadata: dict

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
        )