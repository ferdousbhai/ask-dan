import logging
import os
import json
from datetime import datetime, timezone
from typing import TypedDict, Literal

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

class Delegation(TypedDict):
    delegate_to: Literal["claude", "online"]
    prompt: str

class LLMResponse(TypedDict):
    messages: list[str]
    delegation: Delegation | None

class Message(TypedDict):
    id: int
    role: Literal["user", "assistant"]
    content: str
    metadata: dict
    created_at: int

@app.function(image=image, secrets=[Secret.from_name("google-genai")])
def get_llm_response(
    message: Message,
    conversation_summary: str | None = None,
    model_name: str = "gemini-1.5-flash-latest"
) -> LLMResponse | Exception:
    """
    Get response from Gemini model with delegation capability.
    Returns a dict with immediate messages and optional delegation info.
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
                    "required": ["messages"],
                    "properties": {
                        "messages": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "delegation": {
                            "type": "object",
                            "required": ["delegate_to", "prompt"],
                            "properties": {
                                "delegate_to": {"type": "string", "enum": ["claude", "online"]},
                                "prompt": {"type": "string"}
                            }
                        }
                    }
                }
            )
        )
        
        try:
            response_data = json.loads(result.parts[0].text)
            logging.info(f"LLM {model_name} response data: {response_data}")
            messages = response_data.get("messages", [])
            delegation = response_data.get("delegation")
            return LLMResponse(messages=messages, delegation=delegation)
            
        except Exception as e:
            logging.exception("Error parsing JSON response from Gemini.")
            return e
        
    except Exception as e:
        logging.exception("Error in Gemini API call")
        return e


@app.function(image=image, secrets=[Secret.from_name("perplexity")])
def get_online_model_response(context: str, prompt: str) -> str | Exception:
    from openai import OpenAI

    try:
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
        return response.choices[0].message.content
    except Exception as e:
        logging.exception("Error in Perplexity API call")
        return e


@app.function(image=image, secrets=[Secret.from_name("anthropic")])
def get_claude_response(context: str, prompt: str, model: str = "claude-3-5-sonnet-latest", temperature: float = 1) -> str | Exception:
    from anthropic import Anthropic

    try:
        response = Anthropic().messages.create(
            model=model,
            max_tokens=1024,
            temperature=temperature,
            system=create_system_message("claude", context),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        logging.exception("Error in Claude API call")
        return e


@app.function(image=image, secrets=[Secret.from_name("google-genai")])
def update_conversation_summary(
    current_summary: str | None,
    user_message: Message,
    assistant_message_contents: list[str],
    model_name: str = "gemini-1.5-flash-latest"
) -> str | Exception:
    """Updates conversation summary."""
    import google.generativeai as genai
    
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(model_name)

    if current_summary:
        # Check if topic has changed using function calling
        topic_check = model.generate_content(
            f"""Previous conversation summary: {current_summary}
            New message: {user_message['content']}
            
            Determine if this represents a completely new topic or conversation.""",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "is_new_topic": {"type": "boolean"},
                    }
                }
            )
        )
        
        try:
            result = json.loads(topic_check.parts[0].text)
            if result.get("is_new_topic"):
                logging.info("Topic has changed.")
                # Archive old summary to vector db (lancedb) #TODO
                current_summary = None
        except Exception as e:
            logging.exception("Error checking topic switch")
            # Continue with existing summary if check fails
    
    # Generate new/updated summary
    summary_prompt = f"""Previous summary:
{current_summary or 'Starting new conversation.'}

Latest interaction:
User ({user_message['metadata']['from']['first_name']} {user_message['metadata']['from']['last_name']}): {user_message['content']}
Assistant: {' '.join(assistant_message_contents)}

Create a comprehensive summary of the conversation that:
1. Maintains essential context from previous interactions
2. Integrates new key points from the latest exchange
3. Preserves any information that might be relevant for future responses
4. Preserves any specific preferences or important details about the user

Format the summary as a continuous paragraph without bullet points."""

    try:
        response = model.generate_content(summary_prompt)
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
            Message(
                id=tg_message.get("message_id"),
                role="user",
                content=tg_message.get("text"),
                metadata={
                    "from": tg_message.get("from"),
                    "chat": tg_message.get("chat"),
                },
                created_at=tg_message.get("date"),
            )
        )
    return {"status": "ok"}


@app.function(
    image=image,
    secrets=[Secret.from_name("telegram")],
)
async def process_received_message(message: Message):
    from telegram import Bot
    from telegram.constants import ChatAction

    chat_id = message["metadata"]["chat"]["id"]
    
    try:
        bot = Bot(os.environ["ASK_DAN_BOT_TOKEN"])
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        conv_data = get_conversation_data(chat_id)
        router_response = get_llm_response.remote(message, conv_data.conversation_summary)
        assistant_message_contents = router_response["messages"]
        for msg in assistant_message_contents:
            await bot.send_message(
                text=convert_to_markdown_v2(msg),
                chat_id=chat_id,
                parse_mode="MarkdownV2",
            )

        # Handle delegation
        if router_response.get("delegation"):
            try:
                delegate_fn = {
                    "claude": get_claude_response,
                    "online": get_online_model_response
                }.get(router_response["delegation"]["delegate_to"])
                
                if delegate_fn:
                    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                    response_from_delegate = delegate_fn.remote(
                        conv_data.conversation_summary,
                        router_response["delegation"]["prompt"]
                    )
                    await bot.send_message(
                        text=convert_to_markdown_v2(response_from_delegate),
                        chat_id=chat_id,
                        parse_mode="MarkdownV2",
                    )
                    assistant_message_contents.append(response_from_delegate)
            except Exception as e:
                logging.exception("Error in delegation.")
                await bot.send_message(text="I apologize, but I encountered an error while delegating the question.", chat_id=chat_id)

        # Update conversation summary
        updated_summary = update_conversation_summary.remote(conv_data.conversation_summary, message, assistant_message_contents)
        save_conversation_data(
            chat_id,
            updated_summary
        )
        logging.info(f"updated conversation summary: {updated_summary}")
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        await Bot(os.environ["ASK_DAN_BOT_TOKEN"]).send_message(
            text="I apologize, but I encountered an error. Please try again later.",
            chat_id=chat_id,
        )



