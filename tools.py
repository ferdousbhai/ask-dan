import modal
from pydantic import BaseModel
from datetime import datetime


class TimeFilter(BaseModel):
    start_date: datetime
    end_date: datetime


# TODO: This be in VectorDB
def find_conversation_context(
    conversation_dict: modal.Dict,
    chat_id: int,
    num_conversations: int = 10,
    query: str = "",
    timeperiod: TimeFilter | None = None,
):
    return conversation_dict.get(chat_id)


# TODO: This be in VectorDB
def save_conversation_context(
    conversation_dict: modal.Dict, chat_id: int, context: str, timestamp: datetime
):
    """
    Save the conversation context to the conversation_dict.
    """
    if chat_id not in conversation_dict:
        conversation_dict[chat_id] = {"previous_conversations": []}
    elif "previous_conversations" not in conversation_dict[chat_id]:
        conversation_dict[chat_id]["previous_conversations"] = []

    conversation_dict[chat_id]["previous_conversations"].append(
        {"context": context, "timestamp": timestamp}
    )


# Basic tools: RAG tools to lookup ChatHistory, World Knowledge, ddgs tools
# use reranker to pick top 3.
# What actions can be imported from OpenAI?
