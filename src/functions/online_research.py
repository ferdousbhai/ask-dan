import os
import re
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.environ.get("PERPLEXITY_API_KEY"),
    base_url="https://api.perplexity.ai",
)

async def get_online_research(question: str, model="sonar-reasoning-pro") -> str:
    response_stream = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
        stream=True
    )

    accumulated_text = ""
    async for chunk in response_stream:
        if chunk_content := chunk.choices[0].delta.content:
            accumulated_text += chunk_content
            # Extract the think section and citations, return immediately
            if match := re.search(r'<think>(.*?)</think>', accumulated_text, re.DOTALL):
                sections = []
                sections.append(f'<think>{match.group(1).strip()}</think>')
                try:
                    citations = getattr(chunk, 'citations', [])
                    if citations:
                        sections.append('<citations>\n' + '\n'.join(f'{i+1}) {c}' for i, c in enumerate(citations)) + '</citations>')
                except AttributeError:
                    pass  # Skip citations if attribute doesn't exist
                return "\n\n".join(sections)
