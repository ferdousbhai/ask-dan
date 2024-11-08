import logging
import os

from modal import Secret, App, Image

from src.prompts.templates import create_system_message


app = App("ask-llm")


@app.function(
    image=Image.debian_slim(python_version="3.12").pip_install("openai"),
    secrets=[Secret.from_name("perplexity")],
)
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


@app.function(
    image=Image.debian_slim(python_version="3.12").pip_install("anthropic"),
    secrets=[Secret.from_name("anthropic")],
)
def get_claude_response(
    context: str,
    prompt: str,
    model: str = "claude-3-5-sonnet-latest",
    temperature: float = 1,
) -> str | Exception:
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
