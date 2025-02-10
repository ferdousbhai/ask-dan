import os
from cachetools.func import ttl_cache

@ttl_cache(ttl=60*24*60*60, maxsize=100) # 1 day
async def scrape_url(url: str) -> str | Exception:
    from firecrawl import FirecrawlApp

    try:
        result = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY")).scrape_url(
            url, params={'formats': ['markdown']}
        )

        # Check if result is a dict and has markdown content
        if not isinstance(result, dict):
            return ValueError(f"Expected dict result, got {type(result)}")

        if 'markdown' not in result:
            return ValueError("No markdown content found in scraped result")

        return result['markdown']

    except Exception as e:
        return e