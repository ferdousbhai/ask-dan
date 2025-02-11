from .schema import create_function_response
from ..chat import clear_chat

def start_a_new_conversation(chat_id: int, reason: str = None) -> dict:
    """Start a new conversation by creating a fresh chat instance.

    Args:
        chat_id: The Telegram chat ID
        message: The Telegram message object (needed for system prompt)
        reason: Optional reason for starting new conversation

    Returns:
        dict: Standardized function response
    """
    try:
        clear_chat(chat_id)
        result = f"Started new conversation{f' because: {reason}' if reason else ''}"
        return create_function_response(result=result)
    except Exception as e:
        return create_function_response(error=e)