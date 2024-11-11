import logging

from src.deployed.telegram_bot import chat_memory  # type: modal.Dict


def get_memory_contents() -> dict[int, str]:
    """
    Returns a dictionary of all chat IDs and their corresponding memory contents.
    
    Returns:
        dict[int, str]: A dictionary where keys are chat IDs and values are memory contents
    """
    try:
        return {
            chat_id: data.get("memory_content", "")
            for chat_id, data in chat_memory.items()
        }
    except Exception as e:
        logging.exception("Error retrieving memory contents")
        raise e
    

if __name__ == "__main__":
    memories = get_memory_contents()
    for chat_id, content in memories.items():
        print(f"Chat {chat_id}:")
        print(content)
        print("-" * 50)
