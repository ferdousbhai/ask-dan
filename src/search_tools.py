import logging
from typing import TypedDict
import asyncio
import os
from dotenv import load_dotenv
from cachetools.func import ttl_cache

load_dotenv()

class NewsItem(TypedDict):
    title: str
    description: str
    url: str
    published_date: str

@ttl_cache(ttl=600, maxsize=100)
async def get_news(
    search_term: str,
    search_description: str | None = None,
    max_results: int = 10,
) -> list[NewsItem] | None:
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/news/search",
                params={"q": f"{search_term} {search_description}".strip(), "count": max_results},
                headers={"X-Subscription-Token": os.getenv("BRAVE_API_KEY")},
                timeout=10.0
            )
            response.raise_for_status()
            
            if results := response.json().get("results"):
                return [
                    NewsItem(
                        title=r["title"],
                        description=r["description"],
                        url=r["url"],
                        published_date=r.get("page_age") or r.get("age", ""),
                    ) for r in results
                ]
            return []
            
    except (httpx.TimeoutException, httpx.HTTPError, Exception) as e:
        logging.error(f"Error fetching news: {e}")
        return None

def extract_content(markdown: str) -> str:
    from openai import OpenAI
    
    return OpenAI().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Extract the main article from the following markdown. Do not include any headers, footers, or other irrelevant elements: \n\n{markdown}"}],
    ).choices[0].message.content

@ttl_cache(ttl=60*24*60*60, maxsize=100) # 1 day
async def scrape_url(url: str) -> str | None:
    from firecrawl import FirecrawlApp
    
    try:
        result = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY")).scrape_url(
            url, params={'formats': ['markdown']}
        )
        
        if 'metadata' not in result or 'markdown' not in result:
            raise ValueError(f"Failed to scrape website: {result}")
            
        return extract_content(result['markdown'])
    except Exception as e:
        logging.error(f"Error scraping website: {e}")
        return None
    

if __name__ == "__main__":
    url = "https://www.tesla.com/en_ca"
    content = asyncio.run(scrape_url(url))
    print(content)