import os
from cachetools.func import ttl_cache
from .schema import create_function_response
from firecrawl import FirecrawlApp

@ttl_cache(ttl=60*24*60*60, maxsize=100) # 1 day
async def scrape_url(url: str) -> dict:
    try:
        result = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY")).scrape_url(
            url, params={'formats': ['markdown']}
        )

        if not isinstance(result, dict):
            return create_function_response(
                error=ValueError(f"Expected dict result, got {type(result)}")
            )

        if 'markdown' not in result:
            return create_function_response(
                error=ValueError("No markdown content found in scraped result")
            )

        return create_function_response(result=result['markdown'])

    except Exception as e:
        return create_function_response(error=e)