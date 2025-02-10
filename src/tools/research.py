import os
import re

async def get_online_research(question: str, model="sonar-reasoning-pro") -> str | Exception:
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(
            api_key=os.environ.get("PERPLEXITY_API_KEY"),
            base_url="https://api.perplexity.ai",
        )

        response_stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": question}],
            stream=True
        )

        accumulated_text = ""
        async for response in response_stream:
            if not (content := response.choices[0].delta.content):
                continue

            accumulated_text += content
            if match := re.search(r'<think>(.*?)</think>', accumulated_text, re.DOTALL):
                sections = []
                if response.citations:
                    sections.append("# Search results\n" + "\n".join(f"{i+1}) {c}" for i, c in enumerate(response.citations)))
                sections.append("# Thoughts\n" + match.group(1).strip())
                return "\n\n".join(sections)

        return Exception("No think tag found in response")
    except Exception as e:
        return e