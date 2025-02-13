from google.genai import types


function_declarations = [
    types.FunctionDeclaration(
        name="start_a_new_conversation",
        description="Clear the chat history when the conversation topic changes",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "_": types.Schema(
                    type="STRING",
                    description="The reason for starting a new conversation"
                )
            },
            required=["_"]
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
        name="request_user_location",
        description="Request the user's current location",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "text_to_send": types.Schema(
                    type="STRING",
                    description="The text to send to the user requesting their location"
                )
            },
            required=["text_to_send"]
        )
    )
]

# Wrap function declarations in a Tool object
tools = [types.Tool(function_declarations=function_declarations)]
