from google.genai import types


function_declarations = [
    types.FunctionDeclaration(
        name="start_a_new_conversation",
        description="Clear the chat history when the conversation topic changes",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "reason": types.Schema(
                    type="STRING",
                    description="The reason for starting a new conversation"
                )
            },
            required=["reason"]
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
    ),
    types.FunctionDeclaration(
        name="get_location_info",
        description="Get detailed location information from coordinates",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "coordinates_str": types.Schema(
                    type="STRING",
                    description="Coordinates string in format 'latitude,longitude' (e.g. '37.7955,-122.3937')"
                )
            },
            required=["coordinates_str"]
        )
    ),
    types.FunctionDeclaration(
        name="search_nearby_places",
        description="Search for places near given coordinates",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(
                    type="STRING",
                    description="JSON string containing: coordinates (required, format: 'lat,lon'), keyword (optional), radius (optional, meters, max 50000), place_type (optional)"
                )
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="get_place_details",
        description="Get detailed information about a specific place",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "place_id": types.Schema(
                    type="STRING",
                    description="Google Places ID string"
                )
            },
            required=["place_id"]
        )
    ),
    types.FunctionDeclaration(
        name="contact_dev",
        description="Contact the developer about issues, feature requests, or concerning user behavior",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "issue_type": types.Schema(
                    type="STRING",
                    description="Type of issue (e.g., 'Error Report', 'Feature Request', 'User Report', 'Missing Tool')",
                    enum=["Error Report", "Feature Request", "User Report", "Missing Tool"]
                ),
                "description": types.Schema(
                    type="STRING",
                    description="Detailed description of the issue or request"
                ),
                "user_info": types.Schema(
                    type="STRING",
                    description="Information about the user (if relevant)"
                ),
                "suggested_solution": types.Schema(
                    type="STRING",
                    description="Suggested solution or implementation details (if applicable)"
                )
            },
            required=["issue_type", "description"]
        )
    ),
]

# Wrap function declarations in a Tool object
tools = [types.Tool(function_declarations=function_declarations)]
