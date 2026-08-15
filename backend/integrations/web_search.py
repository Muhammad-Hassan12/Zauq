import re
import urllib.parse
import httpx
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("zauq.web_search")

class WebSearchEngine:
    """
    Universal Web Search and URL Content Reader for Zauq.
    Provides DuckDuckGo live search, Jina Reader URL scraping, and search query extraction.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    async def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Performs a web search via DuckDuckGo HTML endpoint without requiring an API key.
        Returns a list of dicts: [{"title": ..., "url": ..., "snippet": ...}]
        """
        results = []
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                    headers=self.headers
                )
                if response.status_code != 200:
                    logger.warning(f"DuckDuckGo search returned status {response.status_code}")
                    return results

                html = response.text

                # Parse search result blocks from DuckDuckGo HTML
                result_blocks = re.findall(
                    r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
                    html,
                    re.DOTALL
                )

                titles = re.findall(r'<a class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)

                for idx, (raw_url, snippet_html) in enumerate(result_blocks[:max_results]):
                    # Clean snippet
                    snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
                    snippet = snippet.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&lt;", "<").replace("&gt;", ">")

                    # Clean title
                    title = f"Result {idx+1}"
                    if idx < len(titles):
                        title = re.sub(r"<[^>]+>", "", titles[idx]).strip()
                        title = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'")

                    # Extract actual URL from DuckDuckGo redirect
                    actual_url = raw_url
                    if "uddg=" in raw_url:
                        match = re.search(r"uddg=([^&]+)", raw_url)
                        if match:
                            actual_url = urllib.parse.unquote(match.group(1))

                    if actual_url and snippet:
                        results.append({
                            "title": title,
                            "url": actual_url,
                            "snippet": snippet
                        })

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed for '{query}': {e}")

        return results

    async def fetch_url_content(self, target_url: str, max_chars: int = 8000) -> str:
        """
        Fetches and extracts clean readable markdown text from a webpage using Jina Reader (free API).
        Fallback to direct text extraction if Jina is unavailable.
        """
        target_url = target_url.strip()
        if not (target_url.startswith("http://") or target_url.startswith("https://")):
            return "[Invalid URL: Must start with http:// or https://]"

        # Method 1: Jina Reader (https://r.jina.ai/<url>)
        jina_url = f"https://r.jina.ai/{target_url}"
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                res = await client.get(jina_url, headers={"User-Agent": "Zauq-Bot/3.0"})
                if res.status_code == 200 and len(res.text.strip()) > 50:
                    text = res.text.strip()
                    if len(text) > max_chars:
                        text = text[:max_chars] + "\n... [Webpage Content Truncated for Length]"
                    return text
        except Exception as jina_err:
            logger.info(f"Jina reader fallback for {target_url}: {jina_err}")

        # Method 2: Direct HTTP scrape fallback
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.get(target_url, headers=self.headers)
                if res.status_code == 200:
                    # Strip scripts and styles
                    html = re.sub(r"<(script|style).*?</\1>", "", res.text, flags=re.DOTALL | re.IGNORECASE)
                    # Strip HTML tags
                    plain_text = re.sub(r"<[^>]+>", " ", html)
                    # Clean whitespace
                    plain_text = re.sub(r"\s+", " ", plain_text).strip()
                    if len(plain_text) > max_chars:
                        plain_text = plain_text[:max_chars] + "\n... [Webpage Content Truncated for Length]"
                    return plain_text if plain_text else "[Webpage contained no readable text]"
        except Exception as e:
            return f"[Failed to fetch webpage content: {str(e)}]"

        return "[Unable to retrieve content from URL]"

    def extract_urls(self, text: str) -> List[str]:
        """Extracts all http/https URLs from a text string."""
        if not text:
            return []
        pattern = r'https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s()<>]*)*'
        return re.findall(pattern, text)

    def should_search_web(self, query: str) -> bool:
        """Heuristic check if a user query likely requires live search."""
        keywords = [
            "latest", "news", "today", "yesterday", "current", "release", "version",
            "price", "weather", "score", "match", "stock", "update", "released",
            "who is the current", "what happened", "recent", "search for", "google", "browse"
        ]
        q_lower = query.lower()
        return any(kw in q_lower for kw in keywords)

web_search_engine = WebSearchEngine()
