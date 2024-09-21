from datetime import datetime, timezone


def get_system_prompt(
    message: dict,
    context: str | None = None,
    last_message_created_at: int | None = None,
):
    metadata = message["metadata"]
    prompt = (
        f"You are Dan, a kind, helpful assistant. "
        f"You are chatting with {metadata['from']['first_name']} {metadata['from']['last_name']} "
        f"in a {metadata['chat']['type']} chat on telegram. "
        f"Keep responses short and concise. If you need to explain something in more detail, "
        f"you can do so by sending multiple short messages.\n"
        f"Current date and time is {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}.\n"
    )

    if last_message_created_at:
        prompt += f"The last message from the assistant was generated at {datetime.fromtimestamp(last_message_created_at, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}.\n"

    if context:
        prompt += f"\n<context>{context}</context>"

    return prompt


if __name__ == "__main__":
    message = {
        "metadata": {
            "from": {"first_name": "John", "last_name": "Doe"},
            "chat": {"type": "group"},
        }
    }
    print(get_system_prompt(message, None, 1700000000))
