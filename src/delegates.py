import logging
import os
from openai import OpenAI
from anthropic import Anthropic

from src.prompt import create_system_message_content

# Configure logging
logging.basicConfig(level=logging.INFO)

def get_online_model_response(context: str, prompt: str) -> str | Exception:
    """Get response from Perplexity API."""
    try:
        client = OpenAI(
            api_key=os.environ["PERPLEXITY_API_KEY"],
            base_url="https://api.perplexity.ai",
        )

        response = client.chat.completions.create(
            model="llama-3.1-sonar-large-128k-online",
            messages=[
                {"role": "system", "content": create_system_message_content("online", context)},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=1024,
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
    context: str,
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
            max_tokens=1024,
            temperature=temperature,
            system=create_system_message_content("claude", context),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        logging.exception("Error in Claude API call")
        return e