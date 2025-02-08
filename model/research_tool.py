import os

async def get_online_research(question: str, model="sonar-reasoning-pro") -> str | Exception:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.environ.get("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai",
    )

    response_stream = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": question,
            },
        ],
        stream=True
    )

    accumulated_text = ""
    async for response in response_stream:
        if response.choices[0].delta.content:
            chunk = response.choices[0].delta.content
            accumulated_text += chunk

            if '<think>' in accumulated_text and '</think>' in accumulated_text:
                # Extract text between think tags
                start_idx = accumulated_text.find('<think>') + len('<think>')
                end_idx = accumulated_text.find('</think>')
                thought = accumulated_text[start_idx:end_idx].strip()

                if response.citations:
                    thought += "\n\nCitations:\n" + "\n".join(
                        f"{i+1}) {citation}"
                        for i, citation in enumerate(response.citations)
                    )

                return thought

    return Exception("No think tag found!")


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()

    question = "What are the most significant current developments in American politics?"
    print(f"Starting online research for question: {question}")
    response = asyncio.run(get_online_research(question))
    print(response)
