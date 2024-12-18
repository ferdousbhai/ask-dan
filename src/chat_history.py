import os
import json
import logging
from pathlib import Path

# Set storage path
IS_RAILWAY = os.getenv('RAILWAY_ENVIRONMENT') is not None
if IS_RAILWAY:
    BASE_DIR = Path('/data')
else:
    # For local development, use a directory in the project
    BASE_DIR = Path(__file__).parent.parent / 'data'

def _get_chat_file(chat_id: int) -> Path:
    """Get the path for a specific chat's JSON file."""
    return BASE_DIR / f"chat_{chat_id}.json"

async def save_chat_history(chat_id: int, chat_history: list[dict[str, str]]):
    """Save chat history to a JSON file."""
    try:
        file_path = _get_chat_file(chat_id)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.exception("Error saving memory to file")
        raise e

async def get_chat_history(chat_id: int) -> list[dict[str, str]] | None:
    """Retrieve chat history from a JSON file."""
    try:
        file_path = _get_chat_file(chat_id)
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception as e:
        logging.exception("Error retrieving memory from file")
        raise e

async def clear_chat_history(chat_id: int) -> bool:
    """Clear chat history by removing the JSON file."""
    try:
        file_path = _get_chat_file(chat_id)
        if file_path.exists():
            file_path.unlink()  # Delete the file
            logging.info(f"Chat history cleared for chat_id: {chat_id}")
            return True
    except Exception as _:
        logging.exception("Error clearing memory")
    return False