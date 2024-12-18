import os
import logging
import json
from typing import Literal
from PIL import Image
from io import BytesIO
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Message
from src.chat_history import clear_chat_history
from src.delegates import get_online_response, get_claude_response


# LLM interaction
async def get_model_response(user_message: Message, chat_history: list[dict[str, str]] | None = None, model_name: str = os.getenv("DEFAULT_MODEL"), temperature: float = 2.0, api_key: str = os.getenv("GOOGLE_API_KEY")) -> str | Exception:
    """Get response using Gemini's chat mode."""
    
     # Functions for LLM
    async def start_a_new_conversation() -> bool:
        # TODO: save conversation to VectorDB
        return await clear_chat_history(user_message.chat.id)

    async def load_previous_conversation(description: str) -> list[dict[str, str]]:
        # TODO: Load conversation from VectorDB
        # return await load_conversation(user_message.chat.id, description)
        ...
    
    async def delegate_to_model(model: Literal["perplexity", "claude"], prompt: str) -> str:
        delegates = {
            "perplexity": get_online_response,
            "claude": get_claude_response
        }
        if model not in delegates:
            raise ValueError(f"Unknown model: {model}")
        return delegates[model](prompt)
        
    system_instruction = f"""You are a kind, helpful AI assistant named "Dan" deployed on Telegram.
    You are talking to {user_message.from_user.first_name} {user_message.from_user.last_name or ''} in a {user_message.chat.type} chat.
    {f"The user is replying to {user_message.reply_to_message.from_user.first_name}'s message: {user_message.reply_to_message.text or user_message.reply_to_message.caption or ''}" if user_message.reply_to_message else ""}
    - Be direct and clear in your responses
    - Keep responses concise but informative, never more than 4000 characters
    - If you're unsure, acknowledge the uncertainty
    - Use markdown formatting in your responses

    You have access to some tools to help you with your task:
    - If the conversation topic changes, or the user wants to start a new conversation, use the start_a_new_conversation function to clear the conversation history and start a new one
    - If you need to reference any previous conversation, use the load_previous_conversation function to load a conversation from VectorDB
            
    You can delegate certain types of queries to specialized models:
    - Use delegate_to_model("perplexity") for:
        * Current events and real-time information
        * Complex academic or technical questions
        * Questions requiring up-to-date knowledge
    - Use delegate_to_model("claude") for:
        * Complex coding tasks and code review
        * Detailed analysis of technical documents
        * Mathematical problem-solving
            
    When delegating:
    1. Pass a clear, well-formatted prompt to the delegate model
    2. Return the response with appropriate context
    """

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            tools=[start_a_new_conversation, load_previous_conversation, delegate_to_model],
            system_instruction=system_instruction
        )

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=800,
            temperature=temperature,
        )

        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        chat = model.start_chat(history=chat_history if chat_history else [])
        
        prompt_parts = []
        if user_message.photo:
            photo = user_message.photo[-1]
            image = Image.open(BytesIO(await (await photo.get_file()).download_as_bytearray()))
            prompt_parts.extend([
                image,
                user_message.text or user_message.caption or "Please analyze this image and describe what you see."
            ])
        else:
            prompt_parts.append(user_message.text or user_message.caption)

        response = await chat.send_message_async(prompt_parts, generation_config=generation_config, safety_settings=safety_settings)

        # Process function calls
        while any(part.function_call for part in response.parts):
            fn = next(part.function_call for part in response.parts if part.function_call)
            
            # Execute function based on name
            function_map = {
                "start_a_new_conversation": lambda: start_a_new_conversation(),
                "load_previous_conversation": lambda: load_previous_conversation(fn.args["description"]),
                "delegate_to_model": lambda: delegate_to_model(model=fn.args["model_name"], prompt=fn.args["prompt"])
            }
            result = await function_map[fn.name]()
            
            function_response = {
                "role": "function",
                "name": fn.name,
                "content": json.dumps(result)
            }
            response = await chat.send_message_async(function_response, generation_config=generation_config, safety_settings=safety_settings)

        return response.text
        
    except Exception as e:
        logging.exception("Error in Gemini API call")
        return e