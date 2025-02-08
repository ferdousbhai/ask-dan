import os
from cachetools.func import ttl_cache

async def extract_content(markdown: str) -> str:
    from openai import AsyncOpenAI
    response = await AsyncOpenAI().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Extract the main article from the following markdown. Do not include any headers, footers, or other irrelevant elements: \n\n{markdown}"}],
    )
    return response.choices[0].message.content

@ttl_cache(ttl=60*24*60*60, maxsize=100) # 1 day
async def scrape_url(url: str) -> str | Exception:
    from firecrawl import FirecrawlApp

    try:
        result = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY")).scrape_url(
            url, params={'formats': ['markdown']}
        )

        # Check if result is a dict and has markdown content
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict result, got {type(result)}")

        if 'markdown' not in result:
            raise ValueError("No markdown content found in scraped result")

        return await extract_content(result['markdown'])

    except Exception as e:
        raise e


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()

    url = "https://www.tesla.com/en_ca"
    content = asyncio.run(scrape_url(url))
    print(content)