import logging
import json
from pathlib import Path
from .url_tool import scrape_url
from .research_tool import get_online_research
from enum import Enum
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Get the directory containing the current file
current_dir = Path(__file__).parent
with open(current_dir / 'tools.json', 'r') as f:
    tools = json.load(f)

class ToolName(str, Enum):
    NEW_CONVERSATION = "start_a_new_conversation"
    SCRAPE_URL = "scrape_url"
    ONLINE_RESEARCH = "get_online_research"

async def handle_tool_call(tool_call: dict, telegram_update=None, telegram_context=None) -> tuple[str, bool]:
    """Handle a single tool call and return the result and error status.
    If telegram_update and context are provided, also sends intermediate results to the chat."""
    tool_name = tool_call["name"]
    result = ""
    is_error = False

    # Helper function to send intermediate result
    async def send_message(message: str):
        if telegram_update and telegram_context:
            await telegram_update.message.reply_text(message)

    if tool_name == ToolName.SCRAPE_URL:
        await send_message("🌐 Scraping URL ⏳")
        result = await scrape_url(tool_call["input"]["url"])
        if isinstance(result, Exception):
            is_error = True
            result = f"Error scraping URL: {str(result)}"
        result = result if result else "Failed to scrape URL"
        return result, is_error

    if tool_name == ToolName.ONLINE_RESEARCH:
        message = await send_message("🔍 Researching online ⏳")
        result = await get_online_research(tool_call["input"]["question"])
        if isinstance(result, Exception):
            is_error = True
            result = f"Error performing research: {str(result)}"
        result = result if result else "Failed to get online research"

        if telegram_update and telegram_context:
            keyboard = [[
                InlineKeyboardButton("Show Research Details", callback_data=f"show_research_{telegram_update.message.message_id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Store the research result in context.user_data for later retrieval
            telegram_context.user_data[f"research_{telegram_update.message.message_id}"] = result
            # Edit the original "researching" message instead of sending a new one
            await message.edit_text(
                "✅ Research completed. See details?",
                reply_markup=reply_markup
            )
        return result, is_error

    result = f"Unknown tool: {tool_name}"
    return result, True

async def chat_with_model(
    user_message: dict,
    system_prompt: str | None = None,
    chat_history: list[dict] | None = None,
    model_name: str = "claude-3-5-sonnet-latest",
    temperature: float = 1,
    telegram_update=None,
    telegram_context=None,
) -> list[dict] | Exception:
    """Chat with the model and return the full conversation history, handling any tool calls."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()

    try:
        chat_history = chat_history or []
        new_conversation_turns = []

        while True:
            # Prepare message parameters
            message_params = {
                "model": model_name,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": chat_history + [user_message] + new_conversation_turns,
                "tools": tools,
            }

            # Only add system prompt if it's not None
            if system_prompt is not None:
                message_params["system"] = system_prompt

            response = await client.messages.create(**message_params)

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

            # Process tool calls
            tool_calls = [block for block in serializable_content if block["type"] == "tool_use"]
            logging.info(f"Found {len(tool_calls)} tool calls to process")
            tool_result_content = []

            for tool_call in tool_calls:
                logging.info(f"Processing tool call: {tool_call['name']} with input: {tool_call['input']}")

                if tool_call["name"] == ToolName.NEW_CONVERSATION:
                    chat_history = []
                    new_conversation_turns = []
                    tool_result = "Starting a new conversation"
                    is_error = False
                else:
                    tool_result, is_error = await handle_tool_call(
                        tool_call,
                        telegram_update=telegram_update,
                        telegram_context=telegram_context
                    )

                tool_result_content.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": tool_result,
                    "is_error": is_error
                })

            if tool_result_content:
                logging.info(f"Sending {len(tool_result_content)} tool results back to Claude")
                new_conversation_turns.append({
                    "role": "user",
                    "content": tool_result_content
                })

        # Return the full conversation history
        return chat_history + [user_message] + new_conversation_turns

    except Exception as e:
        logging.exception("Error in Anthropic API call")
        return e


# Test
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    mock_message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Hello, I need help shopping for a fun robot"
            }
        ]
    }

    messages = asyncio.run(chat_with_model(mock_message))
    for message in messages:
        for content_block in message['content']:
            logging.info(content_block)
