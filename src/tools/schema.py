from google.genai import types
from typing import Any
import inspect

function_declarations = [
    types.FunctionDeclaration(
        name="start_a_new_conversation",
        description="Clear the chat history when the conversation topic changes",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "reason": types.Schema(
                    type="STRING",
                    description="Optional reason for starting a new conversation"
                )
            },
            required=[]
        )
    ),
    types.FunctionDeclaration(
        name="scrape_url",
        description="Scrape and extract content from a webpage in markdown format",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "url": types.Schema(
                    type="STRING",
                    description="The URL of the webpage to scrape"
                )
            },
            required=["url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_online_research",
        description="Perform online research using Perplexity AI to answer questions with up-to-date information",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "question": types.Schema(
                    type="STRING",
                    description="The research question to be answered"
                )
            },
            required=["question"]
        )
    ),
    types.FunctionDeclaration(
        name="get_user_location",
        description="Request the user's current location",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "reason": types.Schema(
                    type="STRING",
                    description="Optional reason for requesting location"
                )
            },
            required=[]
        )
    )
]

# Wrap function declarations in a Tool object
tools = [types.Tool(function_declarations=function_declarations)]

def create_function_response(result: Any = None, error: Exception = None) -> dict:
    """Create a standardized function response format.

    Automatically determines the function name from the call stack.
    """
    # Get the name of the calling function
    caller_frame = inspect.currentframe().f_back
    function_name = caller_frame.f_code.co_name

    return {
        "name": function_name,
        "response": {
            "result": None if error else result,
            "error": str(error) if error else None
        }
    }
