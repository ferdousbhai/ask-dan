import logging
import os
from openai import OpenAI
from anthropic import Anthropic

from src.prompt import create_system_message_content

logging.basicConfig(level=logging.INFO)

def get_online_model_response(prompt: str, model="llama-3.1-sonar-large-128k-online", temperature=0.8) -> str | Exception:
    """Get response from Perplexity API."""
    try:
        client = OpenAI(
            api_key=os.environ["PERPLEXITY_API_KEY"],
            base_url="https://api.perplexity.ai",
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": create_system_message_content("online")},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=800,
        )
        
        # Extract content and citations
        content = response.choices[0].message.content
        citations = response.citations if hasattr(response, 'citations') else []
        
        # Append citations to the response if they exist
        if citations:
            content += "\n\nSources:\n" + "\n".join(f"- {citation}" for citation in citations)
            
        return content
    except Exception as e:
        logging.exception("Error in Perplexity API call")
        return e

def get_claude_response(
    prompt: str,
    model: str = "claude-3-sonnet-20240229",
    temperature: float = 1,
) -> str | Exception:
    """Get response from Claude API."""
    try:
        response = Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        ).messages.create(
            model=model,
            system=create_system_message_content("claude"),
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=800,
        )
        return response.content[0].text
    except Exception as e:
        logging.exception("Error in Claude API call")
        return e