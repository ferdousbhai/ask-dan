from datetime import datetime, timezone

from modal import Dict
from pydantic import BaseModel


conversation_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)

class ConversationData(BaseModel):
    conversation_summary: str | None = None
    created_at: int | None = None


def get_conversation_data(chat_id: int) -> ConversationData:
    try:
        data = conversation_dict[chat_id]
        return ConversationData(**data)
    except KeyError:
        return ConversationData()


def save_conversation_data(
    chat_id: int, 
    new_summary: str
) -> None:
    conversation_dict[chat_id] = {
        "conversation_summary": new_summary,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
    }
