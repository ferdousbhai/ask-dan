import os
from typing import Final
from telegram import Bot
from telegramify_markdown import telegramify# Assuming you have this utility

DEV_CHAT_ID: Final = int(os.environ.get("DEV_CHAT_ID", "0"))

async def contact_dev(
    issue_type: str,
    description: str,
    user_info: str | None = None,
    suggested_solution: str | None = None
) -> str:
    """Contact the developer with various types of notifications."""
    if not DEV_CHAT_ID:
        return "Error: Developer contact configuration is missing"

    try:
        # Construct the message
        message = (
            f"🚨 *{issue_type}*\n\n"
            f"{description}\n"
        )

        if user_info:
            message += f"\n👤 *User Info:*\n{user_info}"

        if suggested_solution:
            message += f"\n💡 *Suggested Solution:*\n{suggested_solution}"

        # Send message
        async with Bot(os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
            chunks = await telegramify(message)
            for chunk in chunks:
                await bot.send_message(
                    chat_id=DEV_CHAT_ID,
                    text=chunk.content,
                    parse_mode="MarkdownV2"
                )

        return "Developer has been notified"

    except Exception as e:
        return f"Failed to contact developer: {str(e)}"
