import os
from cachetools.func import ttl_cache
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

@ttl_cache(ttl=60*24*60*60, maxsize=100) # 1 day
def scrape_url(url: str, **kwargs) -> str:
    result = app.scrape_url(
        url, params={'formats': ['markdown']}
    )

    return result['markdown']