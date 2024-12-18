import logging
import os
from openai import OpenAI
from anthropic import Anthropic

logging.basicConfig(level=logging.INFO)

def get_online_response(prompt: str, model=os.getenv("ONLINE_MODEL"), temperature=0.8, api_key: str = os.getenv("PERPLEXITY_API_KEY")) -> str | Exception:
    PERPLEXITY_SYSTEM_PROMPT = "You are a real-time information specialist focused on providing current and accurate information."
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai",
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PERPLEXITY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=800,
        )
        
        content = response.choices[0].message.content
        if hasattr(response, 'citations'):
            content += "\n\nSources:\n" + "\n".join(f"- {citation}" for citation in response.citations)
            
        return content
    except Exception as e:
        logging.exception("Error in Perplexity API call")
        return e

def get_claude_response(prompt: str, model: str = os.getenv("CLAUDE_MODEL"), temperature: float = 1, api_key: str = os.getenv("ANTHROPIC_API_KEY")) -> str | Exception:
    CLAUDE_SYSTEM_PROMPT = """You are an AI assistant specializing in detailed analysis,
reasoning, creative tasks, writing, and problem-solving. Focus on accuracy, clarity, and practical application.

Guidelines:
- Be direct and clear
- Use markdown formatting
- Keep responses concise and to the point
- Break down complex concepts
- Include concise code examples where relevant
- Consider performance and trade-offs"""
    
    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            system=CLAUDE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=800,
        )
        return response.content[0].text
    except Exception as e:
        logging.exception("Error in Claude API call")
        return e