import logging
import json
from typing import Any
from enum import Enum
from pathlib import Path
from ..tools.url import scrape_url
from ..tools.research import get_online_research

# Get the directory containing the current file
current_dir = Path(__file__).parent
with open(current_dir / 'tools.json', 'r') as f:
    tools = json.load(f)

class ToolName(str, Enum):
    NEW_CONVERSATION = "start_a_new_conversation"
    SCRAPE_URL = "scrape_url"
    ONLINE_RESEARCH = "get_online_research"

async def handle_tool_call(tool_call: dict[str, Any]) -> tuple[str, bool]:
    """Handle a single tool call and return the result and error status."""
    tool_name = tool_call["name"]

    tool_handlers = {
        ToolName.SCRAPE_URL: lambda: scrape_url(tool_call["input"]["url"]),
        ToolName.ONLINE_RESEARCH: lambda: get_online_research(tool_call["input"]["question"])
    }

    if tool_name not in tool_handlers:
        return f"Unknown tool: {tool_name}", True

    try:
        result = await tool_handlers[tool_name]()
        if isinstance(result, Exception):
            return f"Error with {tool_name}: {str(result)}", True
        return result or f"Failed to execute {tool_name}", False
    except Exception as e:
        return f"Error executing {tool_name}: {str(e)}", True

async def chat_with_model(
    user_message: dict,
    system_prompt: str | None = None,
    chat_history: list[dict] | None = None,
    model_name: str = "claude-3-5-sonnet-latest",
    max_tokens: int = 4096,
    temperature: float = 1,
) -> list[dict] | Exception:
    """Chat with the model and return the full conversation history, handling any tool calls."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()

    try:
        chat_history = chat_history or []
        new_conversation_turns = []

        while True:
            message_params = {
                "model": model_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": chat_history + [user_message] + new_conversation_turns,
                "tools": tools,
            }

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

            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_calls = [block for block in serializable_content if block["type"] == "tool_use"]
            tool_result_content = []

            for tool_call in tool_calls:
                if tool_call["name"] == ToolName.NEW_CONVERSATION:
                    chat_history = []
                    new_conversation_turns = []
                    tool_result = "Starting a new conversation"
                    is_error = False
                else:
                    tool_result, is_error = await handle_tool_call(tool_call)

                tool_result_content.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": tool_result,
                    "is_error": is_error
                })

            if tool_result_content:
                new_conversation_turns.append({
                    "role": "user",
                    "content": tool_result_content
                })

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
