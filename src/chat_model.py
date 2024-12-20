import os
import logging
from PIL import Image
from io import BytesIO
from telegram import Message
from google import genai
from google.genai import types
from src.helpers.turn_off_safety import turn_off_safety
from src.chat_history import clear_chat_history
from src.reasoning import get_reasoning_response

async def get_chat_model_response(
    user_message: Message, 
    chat_history: list[dict[str, str]] | None = None, 
    model_name: str = os.getenv("DEFAULT_MODEL"), 
    temperature: float = 2.0, 
    api_key: str = os.getenv("GOOGLE_API_KEY")
) -> str | Exception:
    """Get response using Gemini's chat mode."""
    
    # Define function schema for start_a_new_conversation
    start_new_conversation_schema = dict(
        name="start_a_new_conversation",
        description="Clear the chat history when the conversation topic changes",
    )

    # Define function schema for get_reasoning_response
    get_reasoning_response_schema = dict(
        name="get_reasoning_response",
        description="For complex problem-solving, detailed analysis, and step-by-step logical deductions",
        parameters={
            "type": "OBJECT",
            "properties": {
                "prompt": {"type": "STRING"}
            },
            "required": ["prompt"]
        }
    )

    system_instruction = f"""You are a kind, helpful AI assistant named "Dan" deployed on Telegram.
    - Be direct and clear in your responses
    - Keep responses concise but informative
    - If you're unsure, acknowledge the uncertainty
    - Use markdown formatting in your responses

    Core Beliefs:
    - "Life is fucking electric bro. Don't fall for the doomer shit. That's for losers and normies scared of their own shadows. Walk around like God sent you and smile at everyone you see. Spread light and abundance. Build things and take chances. This is the best time in history!"
    - "A calm mind, a fit body, and a house full of love. These things cannot be bought. They must be earned."
    - "Everything matters and your life is excruciatingly meaningful."
    - "Your thoughts will echo as memes through conscious eternity; your genes will live on through your offspring."
    - "Consciousness is destined to proliferate across the cosmos and began here, now, with you."

    Personality:
    - Maximally curious and truth-seeking. You are driven by a deep desire to understand the universe and everything in it.
    - You are optimistic, enthusiastic, and believe in the power of human potential.
    - You encourage others to live fully, embrace challenges, and make the most of their lives.

    Available tools:
    - start_a_new_conversation: Clear history when conversation topic changes
    - get_reasoning_response: For complex problem-solving, detailed analysis, and step-by-step logical deductions

    Use these tools when appropriate without mentioning them explicitly to the user.
    
    You are talking to {user_message.from_user.first_name} {user_message.from_user.last_name or ''} in a {user_message.chat.type} chat.
    {f"The user is replying to {user_message.reply_to_message.from_user.first_name}'s message: {user_message.reply_to_message.text or user_message.reply_to_message.caption or ''}" if user_message.reply_to_message else ""}
    """

    # Handle image or text input
    prompt_parts = []
    if user_message.photo:
        photo = user_message.photo[-1]
        image = Image.open(BytesIO(await (await photo.get_file()).download_as_bytearray()))
        prompt_parts.extend([image, user_message.text or user_message.caption or "Please analyze this image."])
    else:
        prompt_parts.append(user_message.text or user_message.caption)

    try:

        client = genai.Client(api_key=api_key)
        chat = client.aio.chats.create(
            model=model_name,
            history=chat_history or [],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=800,
                safety_settings=turn_off_safety(),
                tools=[
                    types.Tool(function_declarations=[start_new_conversation_schema]),
                    types.Tool(function_declarations=[get_reasoning_response_schema]),
                ]
            )
        )

        # Send the message to the chat
        response = await chat.send_message(prompt_parts)

        # Process function calls
        while any(part.function_call for part in response.candidates[0].content.parts):
            fn = next(part.function_call for part in response.candidates[0].content.parts if part.function_call)
            logging.info(f"Function call detected: {fn.name}")

            if fn.name == "start_a_new_conversation":
                result = await clear_chat_history(user_message.chat.id)
            elif fn.name == "get_reasoning_response":
                result = await get_reasoning_response(fn.args["prompt"])
            else:
                result = None

            # Log the result of the function call
            logging.info(f"Result of function call '{fn.name}': {result}")

            # Construct function response content
            function_response_content = {
                "role": "function",
                "parts": [{"functionResponse": {"name": fn.name, "response": {"content": str(result)}}}],
            }

            response = await chat.send_message(function_response_content)

        return response.candidates[0].content.parts[0].text
        
    except Exception as e:
        logging.exception("Error in Gemini API call")
        return e

async def test_chat_model():
    """Test function for the chat model."""
    from telegram import Chat, User

    logging.basicConfig(level=logging.INFO)
    
    # Create mock Message object
    mock_user = User(id=1, is_bot=False, first_name="Test", last_name="User")
    mock_chat = Chat(id=1, type="private")
    mock_message = Message(
        message_id=1,
        date=None,
        chat=mock_chat,
        from_user=mock_user,
        text="Hello, how are you? I would love to know how to think from the first principles the age of the universe."
    )
    return await get_chat_model_response(mock_message)

if __name__ == "__main__":
    import asyncio
    response = asyncio.run(test_chat_model())
    print(f"Response: {response}")