import logging
import os
import json
from datetime import datetime, timezone

from fastapi import Request
from modal import App, Image, Function, Secret, web_endpoint

from utils.conversation import get_conversation_data, save_conversation_data
from utils.markdown_v2 import convert_to_markdown_v2
from utils.prompt_templates import create_system_message

logging.basicConfig(level=logging.INFO)


app = App("ask-dan-telegram-bot")

image = Image.debian_slim(python_version="3.12").run_commands(
    "pip install -U pydantic fastapi google-generativeai openai anthropic groq python-telegram-bot"
)


@app.function(image=image, secrets=[Secret.from_name("google-genai")])
def get_llm_response(
    chat_id: int, 
    message: dict,
    conversation_summary: str | None = None,
    model_name: str = "gemini-1.5-flash-8b-latest"
) -> list[str]:
    """
    Get response from Gemini model with delegation capability.
    """
    import google.generativeai as genai
        
    system_message = create_system_message(
        "router", 
        conversation_summary, 
        metadata={
            "user": f"{message['metadata']['from']['first_name']} {message['metadata']['from']['last_name']}",
            "chat_type": message['metadata']["chat"]["type"],
            "current_time": datetime.now(timezone.utc).isoformat(),
        }
    )
    
    try:
        model = genai.GenerativeModel(model_name)
        result = model.generate_content(
            f"{system_message}\n\n{message['content']}",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "response": {
                            "type": "object",
                            "properties": {
                                "delegate_to": {"type": "string", "enum": ["claude", "online"]},
                                "prompt": {"type": "string"}
                            }
                        },
                        "messages": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    }
                }
            )
        )
        try:
            response = json.loads(result.parts[0].text).get("response")
            logging.info(f"Gemini Response: {response}")
        except Exception as e:
            logging.exception("Error parsing JSON response from Gemini.")
            return ["I apologize, but I encountered an error."]
        
        if isinstance(response, dict) and "delegate_to" in response and "prompt" in response:
            try:
                delegate_fn = {
                    "claude": get_claude_response,
                    "online": get_online_model_response
                }.get(response["delegate_to"])
                
                if delegate_fn:
                    return delegate_fn.remote(
                        message, 
                        conversation_summary,
                        response["prompt"]
                    )
                return ["I apologize, but I couldn't delegate the request."]
            except Exception as e:
                logging.exception("Error in delegation.")
                return ["I apologize, but I encountered an error while delegating the question."]
        return response
    except Exception as e:
        logging.exception("Error in Gemini API call")
        return ["I apologize, but I encountered an error while processing your request."]


@app.function(image=image, secrets=[Secret.from_name("perplexity")])
def get_online_model_response(message, context, prompt: str) -> list[str]:
    from openai import OpenAI
    
    client = OpenAI(
        api_key=os.environ["PERPLEXITY_API_KEY"],
        base_url="https://api.perplexity.ai",
    )

    response = client.chat.completions.create(
        model="llama-3.1-sonar-large-128k-online",
        messages=[
            {"role": "system", "content": create_system_message("online", context)},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=1024,
    )

    return [response.choices[0].message.content]


@app.function(image=image, secrets=[Secret.from_name("anthropic")])
def get_claude_response(message, context, prompt: str, model: str = "claude-3-5-sonnet-latest", temperature: float = 1) -> list[str]:
    from anthropic import Anthropic

    response = Anthropic().messages.create(
        model=model,
        max_tokens=1024,
        temperature=temperature,
        system=create_system_message("claude", context),
        messages=[{"role": "user", "content": prompt}],
    )

    return [response.content[0].text]


@app.function(image=image, secrets=[Secret.from_name("google-genai")])
def update_conversation_summary(
    current_summary: str | None,
    user_message: dict,
    assistant_messages: list[str],
    model_name: str = "gemini-1.5-flash-latest"
) -> str | Exception:
    """
    Updates conversation summary to maintain context.
    
    Args:
        current_summary: Existing conversation summary or None
        user_message: Dictionary containing user's message and metadata
        assistant_messages: List of assistant responses
    
    Returns:
        str: Updated conversation summary
    """
    import google.generativeai as genai
    
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(model_name)
    prompt = f"""{current_summary or ''}

New interaction:
{user_message['metadata']['from']['first_name']} {user_message['metadata']['from']['last_name']}: {user_message['content']}
Assistant: {' '.join(assistant_messages)}

Create a brief, focused summary of the conversation that captures key points and context.
Keep the summary concise but informative, focusing on the most relevant details that may be needed for future context."""

    try:
        response = model.generate_content(prompt)
        return response.parts[0].text
    except Exception as e:
        logging.exception("Error in Gemini API call")
        return e


@app.function()
@web_endpoint(method="POST")
async def webhook(request: Request):
    data = await request.json()
    tg_message = data["message"]
    logging.info(f"Received telegram message: {tg_message}")

    if tg_message and tg_message.get("text"):
        process_received_message.spawn(
            {
                "id": tg_message.get("message_id"),
                "role": "user",
                "content": tg_message.get("text"),
                "metadata": {
                    "from": tg_message.get("from"),
                    "chat": tg_message.get("chat"),
                },
                "created_at": tg_message.get("date"),
            }
        )
    return {"status": "ok"}


@app.function(
    image=image,
    secrets=[Secret.from_name("telegram")],
)
async def process_received_message(message: dict):
    try:
        from telegram import Bot
        from telegram.constants import ChatAction

        chat_id = message["metadata"]["chat"]["id"]
        bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        conv_data = get_conversation_data(chat_id)
        assistant_messages = get_llm_response.remote(chat_id, message, conv_data.conversation_summary)
        
        for message in assistant_messages:
            await bot.send_message(
                text=convert_to_markdown_v2(message),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )

        save_conversation_data(
            chat_id,
            update_conversation_summary.remote(conv_data.conversation_summary, message, assistant_messages)
        )
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        await Bot(os.environ["ASK_DAN_BOT_TOKEN"]).send_message(
            text="I apologize, but I encountered an error. Please try again later.",
            chat_id=message["metadata"]["chat"]["id"],
        )


