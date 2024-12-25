import logging
import base64
import json
import re
from telegram import Message as TelegramMessage
from src.system_prompt import get_system_prompt
from src.search_tools import get_news, scrape_url

with open('src/tools.json', 'r') as f:
    tools = json.load(f)


def extract_dan_response(text: str, tag: str = "DAN_RESPONSE") -> str:
    """Extract the text content from within DAN_RESPONSE tags.
    If tags are not found, return the original text with some cleanup."""
    match = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback: If no tags found, try to clean up the text
    # Remove any other XML-style tags that might be present
    cleaned_text = re.sub(r'<[^>]+>', '', text)
    return cleaned_text.strip()


async def get_model_response(
    telegram_message: TelegramMessage,
    chat_history: list[dict] | None = None,
    model_name: str = "claude-3-5-sonnet-latest",
    temperature: float = 1,
) -> list[dict] | Exception:
    from anthropic import AsyncAnthropic

    user_message_content_blocks = []

    if telegram_message.photo:
        photo = telegram_message.photo[-1]
        image_bytes = await (await photo.get_file()).download_as_bytearray()
        user_message_content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode('utf-8'),
            }
        })

    message_text = telegram_message.text or telegram_message.caption
    if message_text:
        user_message_content_blocks.append({
            "type": "text",
            "text": message_text
        })

    try:
        new_conversation_turns = []
        user_message = {"role": "user", "content": user_message_content_blocks}

        while True:
            response = await AsyncAnthropic().messages.create(
                model=model_name,
                max_tokens=4096,
                temperature=temperature,
                system=get_system_prompt(telegram_message),
                messages=(chat_history or []) + [user_message] + new_conversation_turns,
                tools=tools,
            )

            # Convert response content to serializable format
            serializable_content = []
            for block in response.content:
                if block.type == "text":
                    serializable_content.append({
                        "type": "text",
                        "text": block.text
                    })
                elif block.type == "tool_use":
                    serializable_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })

            new_conversation_turns.append({
                "role": "assistant",
                "content": serializable_content
            })

            # break the loop if no tool calls are needed
            if response.stop_reason != "tool_use":
                break

            # Process tool calls - simplified since we already have the tool calls in serializable_content
            tool_calls = [block for block in serializable_content if block["type"] == "tool_use"]
            logging.info(f"Found {len(tool_calls)} tool calls to process")
            tool_result_content = []

            for tool_call in tool_calls:
                logging.info(f"Processing tool call: {tool_call['name']} with input: {tool_call['input']}")
                try:
                    tool_result = None
                    if tool_call["name"] == "start_a_new_conversation":
                        chat_history = []
                        tool_result = "Conversation history cleared"
                    if tool_call["name"] == "get_news":
                        news_items = await get_news(
                            search_term=tool_call["input"]["search_term"],
                            search_description=tool_call["input"].get("search_description")
                        )
                        tool_result = json.dumps(news_items, indent=2) if news_items else "No news found"
                    if tool_call["name"] == "scrape_url":
                        scraped_content = await scrape_url(tool_call["input"]["url"])
                        tool_result = scraped_content if scraped_content else "Failed to scrape URL"

                    if tool_result:
                        tool_result_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": tool_result
                        })
                except Exception as e:
                    logging.error(f"Error processing tool {tool_call['name']}: {str(e)}")
                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call["id"],
                        "content": str(e),
                        "is_error": True
                    })

            if tool_result_content:
                logging.info(f"Sending {len(tool_result_content)} tool results back to Claude")
                new_conversation_turns.append({
                    "role": "user",
                    "content": tool_result_content
                })

        # Return the complete conversation including the final response
        return (chat_history or []) + [user_message] + new_conversation_turns

    except Exception as e:
        logging.exception("Error in Anthropic API call")
        return e


# Test
if __name__ == "__main__":
    import asyncio
    from telegram import Chat, User
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    mock_user = User(id=1, is_bot=False, first_name="Test", last_name="User")
    mock_chat = Chat(id=1, type="private")
    mock_message = TelegramMessage(
        message_id=1,
        date=None,
        chat=mock_chat,
        from_user=mock_user,
        text="Hello, what's the latest with google?"
    )

    messages = asyncio.run(get_model_response(mock_message))
    for message in messages:
        for content_block in message['content']:
            logging.info(content_block)
